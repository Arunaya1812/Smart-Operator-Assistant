from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db import connect

CHROMA_DIR = Path(__file__).resolve().parent / "chroma_data"
MANUAL_PATH = Path(__file__).resolve().parent / "manual.md"
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
UNKNOWN_ANSWER = "I do not have information about that. Please connect with your supervisor"

OPERATOR_CONTEXT_TERMS = {
    "app", "assistant", "battery", "belt", "boom", "brake", "bucket", "cab", "cable", "camera",
    "complaint", "coolant", "dashboard", "defect", "dig", "drowsiness", "engine", "excavator",
    "grading", "hazard", "hydraulic", "idle", "incident", "lesson", "lift", "loader", "machine",
    "maintenance", "metric", "oil", "operator", "parking", "power", "profile", "pump", "reverse",
    "rollover", "safety", "seatbelt", "shift", "slope", "speed", "stall", "steering", "supervisor",
    "task", "ticket", "training", "trench", "truck", "video", "weather", "wind",
}
INAPPROPRIATE_TERMS = {
    "porn", "sexual", "nude", "kill", "murder", "hurt someone", "attack someone", "weapon",
    "hate speech", "racial slur",
}
STOP_WORDS = {
    "a", "about", "an", "and", "are", "can", "do", "for", "how", "i", "if", "in", "is", "it",
    "me", "my", "of", "on", "please", "should", "that", "the", "this", "to", "what", "when",
    "where", "which", "with", "you",
}
GENERIC_EVIDENCE_TERMS = {"app", "assistant", "help", "machine", "operate", "operation", "operator", "safety", "use"}


def _has_operator_context(question: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
    return bool(tokens & OPERATOR_CONTEXT_TERMS)


def _is_inappropriate(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in INAPPROPRIATE_TERMS)


def _retrieval_has_evidence(question: str, found: list[tuple[str, str]]) -> bool:
    query_tokens = set(re.findall(r"[a-z0-9]+", question.lower())) - STOP_WORDS - GENERIC_EVIDENCE_TERMS
    if not query_tokens:
        return False
    return any(query_tokens & set(re.findall(r"[a-z0-9]+", text.lower())) for _, text in found[:3])


def manual_sections() -> list[tuple[str, str]]:
    text = MANUAL_PATH.read_text(encoding="utf-8")
    sections = []
    for block in re.split(r"(?=^## )", text, flags=re.MULTILINE):
        if not block.startswith("## "):
            continue
        title, _, body = block.partition("\n")
        heading = title.removeprefix("## ").strip()
        slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
        sections.append((f"manual-{slug}", f"Operator manual, {heading}: {body.strip()}"))
    return sections


def _intent_answer(question: str, operator_id: int | None) -> dict | None:
    q = " ".join(question.lower().strip().split())
    with connect() as conn:
        operator = conn.execute("SELECT name,expertise FROM operators WHERE id=?", (operator_id,)).fetchone() if operator_id else None

        if re.match(r"^(hi|hello|hey|good morning|good afternoon|good evening|namaste)\b", q):
            name = operator["name"].split()[0] if operator else "operator"
            return {"answer": f"Hello, {name}. I can help with today’s tasks, machine guidance, safety problems, training, complaints, and navigating the app.", "sources": ["assistant-capabilities"], "mode": "intent"}

        task_phrases = ("tasks left", "tasks remaining", "how many tasks", "work left", "remaining today")
        if any(phrase in q for phrase in task_phrases) and operator_id:
            today = datetime.now(IST).date().isoformat()
            rows = conn.execute("SELECT title,status FROM tasks WHERE operator_id=? AND day=? ORDER BY planned_start_hour", (operator_id, today)).fetchall()
            remaining = [row["title"] for row in rows if row["status"] != "completed"]
            active = [row["title"] for row in rows if row["status"] == "in_progress"]
            if not rows:
                answer = "I could not find a task plan for today. Open Tasks to confirm the current assignment."
            elif not remaining:
                answer = "You have completed all tasks assigned for today."
            else:
                active_text = f" {active[0]} is currently in progress." if active else ""
                answer = f"You have {len(remaining)} task{'s' if len(remaining) != 1 else ''} left today: {', '.join(remaining)}.{active_text}"
            return {"answer": answer, "sources": ["live-task-status"], "mode": "intent"}

        # Statements about a hazard happening now trigger automatic escalation.
        # Educational "what if" questions continue to receive manual guidance.
        active_hazards = [
            (r"\b(i am|i'm|feeling)\s+(drowsy|sleepy|too tired)\b", "operator fatigue",
             "Stop the machine safely, lower the attachments, and remain stopped. The drowsiness response and supervisor workflow must be started now."),
            (r"\b(machine|excavator|loader)\b.*\b(is |has started )?(tipping|rolling over)\b", "rollover stability",
             "Lower the bucket to the ground, stay in the seat with the belt fastened, and never jump from the machine."),
            (r"\b(boom|machine|bucket)\b.*\b(hit|contacted|touched)\b.*\b(power line|overhead cable|electrical line)\b", "electrical contact",
             "Stay in the cab, warn everyone to keep away, and wait for the power to be isolated."),
            (r"\b(person|someone|worker|pedestrian)\b.*\b(within|inside|too close|blind spot|swing radius)\b", "proximity hazard",
             "Stop all movement, sound the horn, and resume only after the person is clear and you have eye contact."),
            (r"\b(machine|engine|cab|battery)\b.*\b(on fire|smoking|smoke|burning)\b", "fire or smoke",
             "Stop work immediately, move only if required for immediate safety, and follow the site emergency procedure."),
        ]
        for pattern, component, answer in active_hazards:
            if re.search(pattern, q):
                return {"answer": answer, "sources": ["operator-manual-critical-response"], "mode": "intent",
                        "critical_safety": True, "component": component}

        if any(phrase in q for phrase in ("i am scared", "i'm scared", "i feel scared", "i am nervous", "i'm nervous", "i feel anxious")):
            name = operator["name"].split()[0] if operator else "operator"
            return {"answer": f"It is okay to feel that way, {name}. Pause, take a breath, and work through one safe step at a time. You have completed the checks and you can ask me for guidance whenever you need it.",
                    "sources": ["operator-wellbeing"], "mode": "motivation"}

        if any(phrase in q for phrase in ("long day", "rough day", "hard day", "difficult day", "feeling discouraged", "i messed up", "i made a mistake")):
            name = operator["name"].split()[0] if operator else "operator"
            return {"answer": f"You have handled a lot today, {name}. Focus on finishing safely, not perfectly. Every careful check and every reported problem is good work.",
                    "sources": ["operator-wellbeing"], "mode": "motivation"}

        issue_words = ("broke", "broken", "problem", "fault", "failed", "not working", "stopped working", "damaged")
        if any(word in q for word in issue_words):
            critical = any(word in q for word in ("seatbelt", "seat belt", "brake", "steering", "alarm", "cable", "hydraulic", "rollover"))
            if critical:
                answer = "Stop the machine in a safe position and do not continue the task. Open Safety, select Report a defect, and create a maintenance complaint. Because this can affect safe operation, also use Connect to supervisor in the Assistant."
            else:
                answer = "Pause the task and assess the condition safely. Open Safety and use Report a defect to create a maintenance complaint. If the issue prevents safe work or you are uncertain, connect to a supervisor before continuing."
            component = next((name for name in ("seatbelt", "brake", "steering", "alarm", "cable", "hydraulic") if name in q), "machine component")
            return {"answer": answer, "sources": ["manual-reporting-defects", "maintenance-complaints"], "mode": "intent",
                    "critical_safety": critical, "component": component}

        navigation_terms = ("navigate", "where do i", "where can i", "which page", "which screen", "open the", "find the")
        if any(term in q for term in navigation_terms) and any(term in q for term in ("app", "task", "training", "safety", "complaint", "profile", "assistant", "metric", "efficiency", "incident")):
            destinations = [
                (("task",), "Tasks for today’s work, checks, and task completion"),
                (("training", "video", "lesson"), "Training for videos and completed lessons"),
                (("safety", "complaint", "incident", "defect"), "Safety for incidents, manual tests, and Report a defect"),
                (("metric", "efficiency", "productivity"), "Machine metrics for daily, weekly, and monthly machine results"),
                (("profile", "points"), "Profile for points, expertise, machine assignment, and demo operator selection"),
                (("assistant", "chat"), "Assistant for questions and supervisor escalation"),
            ]
            matches = [description for terms, description in destinations if any(term in q for term in terms)]
            answer = "Use the left navigation. " + ("; ".join(matches) if matches else "Overview shows the shift summary, Tasks shows work, Training shows lessons, Safety shows incidents and complaints, Machine metrics shows machine performance, and Profile shows account details.") + "."
            return {"answer": answer, "sources": ["app-navigation"], "mode": "intent"}

        how_to = q.startswith("how to ") or q.startswith("how do i ") or q.startswith("how should i ")
        if how_to:
            manual = _verified_manual_answer(question)
            if manual:
                answer, source = manual
                return {"answer": answer, "sources": [source], "mode": "verified_local"}
            if not _has_operator_context(question):
                return {"answer": UNKNOWN_ANSWER, "sources": [], "mode": "unknown"}
            expertise = operator["expertise"] if operator else "trainee"
            if expertise == "trainee":
                answer = "Open Training and review the How to use the machine video before attempting that procedure. Also review Safety hazards if the procedure affects people, stability, blind spots, or electrical clearance."
            else:
                answer = "Open Training to review any completed machine lessons available in your library. If the procedure is not covered there, stop and connect to a supervisor for site-specific guidance."
            return {"answer": answer, "sources": ["training-hub", "manual-safe-operation"], "mode": "intent"}
    return None


def corpus() -> list[tuple[str, str]]:
    docs = manual_sections()
    with connect() as conn:
        for row in conn.execute("SELECT id,day,title,status,predicted_minutes,actual_minutes FROM tasks ORDER BY day DESC LIMIT 80"):
            docs.append((f"task-{row[0]}", f"Task log on {row[1]}: {row[2]} was {row[3]}. Predicted duration {row[4]:.1f} minutes. Actual duration {row[5] if row[5] is not None else 'not completed'} minutes."))
        for row in conn.execute("SELECT day,machine_id,efficiency,completion_rate,idle_minutes,incident_count FROM daily_metrics ORDER BY day DESC LIMIT 80"):
            docs.append((f"efficiency-{row[0]}-{row[1]}", f"Machine {row[1]} efficiency on {row[0]} was {row[2]:.1f} percent. Completion rate {row[3]*100:.0f} percent, idle time {row[4]:.1f} minutes, incidents {row[5]}."))
    return docs


def rebuild_index() -> bool:
    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            client.delete_collection("operator_knowledge")
        except Exception:
            pass
        embedding = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        collection = client.create_collection("operator_knowledge", embedding_function=embedding)
        docs = corpus()
        collection.add(ids=[x[0] for x in docs], documents=[x[1] for x in docs], metadatas=[{"source": x[0]} for x in docs])
        return True
    except Exception:
        return False


def _lexical_retrieve(question: str, count: int = 4) -> list[tuple[str, str]]:
    words = set(re.findall(r"[a-z0-9]+", question.lower()))
    scored = []
    for source, text in corpus():
        tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
        scored.append((len(words & tokens), source, text))
    return [(source, text) for _, source, text in sorted(scored, reverse=True)[:count]]


def retrieve(question: str) -> list[tuple[str, str]]:
    lexical = _lexical_retrieve(question, count=6)
    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        embedding = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        collection = client.get_collection("operator_knowledge", embedding_function=embedding)
        result = collection.query(query_texts=[question], n_results=6)
        semantic = [(m.get("source", "knowledge"), d) for m, d in zip(result["metadatas"][0], result["documents"][0])]
        # Hybrid retrieval keeps exact log terms while retaining semantic matches.
        words = set(re.findall(r"[a-z0-9]+", question.lower()))
        unique = {source: text for source, text in semantic + lexical}
        ranked = sorted(unique.items(), key=lambda item: len(words & set(re.findall(r"[a-z0-9]+", item[1].lower()))), reverse=True)
        return ranked[:5]
    except Exception:
        return lexical[:5]


def _verified_manual_answer(question: str) -> tuple[str, str] | None:
    q = question.lower()
    routes = [
        (("hydraulic temperature", "hydraulic hot", "pump wear", "whining pump", "oil pressure"), "manual-hydraulic-system-and-warning-signs-of-pump-wear", "Normal hydraulic oil temperature is 55 to 80 C. Above 85 C, reduce the load and check the cooler. Rising vibration, pump whining, oil pressure below 330 kPa, or slow cylinders require a hydraulic pump maintenance ticket."),
        (("overheat", "too hot", "high temperature", "engine hot"), "manual-hydraulic-system-and-warning-signs-of-pump-wear", "Reduce the load and check the cooler for blockage. If the dashboard shows elevated breakdown risk, finish the current cycle, avoid heavy digging, and raise a hydraulic pump maintenance ticket."),
        (("drowsy", "drowsiness", "sleepy", "tired", "fatigue"), "manual-drowsiness-and-fatigue", "Stop safely, lower the attachments, and tell your supervisor. At a drowsiness signal above 0.70 the system slows and stops the machine, sounds the buzzer, and alerts site safety. Take a break before acknowledging it."),
        (("seatbelt", "seat belt", "restraint"), "manual-seatbelt", "Fasten the seatbelt before starting and keep it fastened whenever the machine moves or an attachment operates. Stop movement immediately if it opens or fails."),
        (("speed limit", "how fast", "maximum speed"), "manual-speed-limits", "The backhoe loader limit is 15 km/h and the excavator travel limit is 4 km/h. Reduce speed on slopes, soft ground, and near people, and carry the bucket low."),
        (("blind spot", "person nearby", "proximity", "personnel", "swing radius"), "manual-proximity-and-blind-spots", "Keep everyone outside the swing radius. If a person is within 5 m, stop all movement and sound the horn. Resume only when they are clear and you have eye contact."),
        (("power line", "overhead cable", "boom contacts", "electrical line"), "manual-overhead-power-lines", "Keep at least 3 m from an overhead cable and use a spotter within 10 m. If contact occurs, stay in the cab, warn others away, and wait for power isolation."),
        (("rollover", "slope", "unstable ground", "machine tipping", "side slope"), "manual-slopes-and-rollover", "Travel straight up or down slopes, never across them, and do not use a side slope above 15 degrees. If tipping starts, lower the bucket, stay belted in the seat, and never jump."),
        (("battery", "low charge", "charge below"), "manual-battery-and-charge", "Below 20 percent battery charge, avoid shutting down away from the service area because the machine may not restart. Raise a maintenance ticket."),
        (("engine stall", "stalled", "keeps stalling"), "manual-engine-stalls", "Lower the attachment, return controls to neutral, restart, and take a smaller bite. A stall usually means excessive bucket load or low engine speed. Report repeated stalls."),
        (("trench", "trenching", "spoil"), "manual-trenching", "Keep spoil at least 1 m from the edge. Do not trench in rain above 10 mm. Check wall cracks after each pass, and use shoring before anyone enters a trench deeper than 1.5 m."),
        (("load truck", "truck loading", "haul truck"), "manual-truck-loading", "Load from the side or rear, never swing over the cab, spread the load evenly, and stay within the truck rating."),
        (("lift pipe", "pipe laying", "lifting", "sling", "tag line"), "manual-lifting-and-pipe-laying", "Use the lift chart for the current boom position, certified slings, and a tag line. Do not lift when wind exceeds 30 km/h."),
        (("grading", "grade surface"), "manual-grading", "Do not schedule grading when rain exceeds 5 mm because the surface cannot hold a level."),
        (("idle", "idling"), "manual-idling", "Idle for no more than five minutes. For a longer wait, lower attachments and shut down. Idle time reduces the machine efficiency score."),
        (("efficiency score", "machine efficiency"), "manual-machine-efficiency-score", "Machine efficiency is 35 percent task completion, 30 percent actual versus predicted time, 20 percent idle time, and 15 percent incident count. It measures the machine, not the operator."),
        (("report defect", "maintenance ticket", "complaint"), "manual-reporting-defects", "Open Safety and use Report a defect, or raise a ticket from a safety alert. Tickets progress from open to in progress to resolved. Never operate with an open brake or steering ticket."),
        (("shut down", "shutdown", "park machine"), "manual-shutdown", "Park on firm level ground, lower all attachments, neutralize controls, apply the parking brake, idle for two minutes to cool the turbocharger, then stop the engine and remove the key."),
        (("pre-start", "prestart", "before start", "walk around", "inspection"), "manual-pre-start-walk-around-check", "Check tyres or tracks, leaks, lights, horn, reversing alarm, brakes, oils, coolant, mirrors, and cameras. Test brakes on level ground. Do not start if a brake or steering check fails; report the defect."),
    ]
    for terms, source, answer in routes:
        if any(term in q for term in terms):
            return answer, source
    return None


def answer_question(question: str, operator_id: int | None = None) -> dict:
    intent = _intent_answer(question, operator_id)
    if intent:
        return intent
    verified = _verified_manual_answer(question)
    if verified:
        answer, source = verified
        return {"answer": answer, "sources": [source], "mode": "verified_local"}
    if _is_inappropriate(question) or not _has_operator_context(question):
        return {"answer": UNKNOWN_ANSWER, "sources": [], "mode": "unknown"}
    found = retrieve(question)
    if not _retrieval_has_evidence(question, found):
        return {"answer": UNKNOWN_ANSWER, "sources": [], "mode": "unknown"}
    context = "\n".join(f"[{source}] {text}" for source, text in found)
    fallback = f"Based on [{found[0][0]}]: {found[0][1]}" if found else UNKNOWN_ANSWER
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"answer": fallback, "sources": [s for s, _ in found], "mode": "offline"}
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=0.0,
            max_tokens=220,
            messages=[
                {"role": "system", "content": "Answer as a concise heavy-machinery assistant. Use only the supplied context. Cite at least one supplied source id in square brackets. If the context does not answer the question, say that clearly and advise a safe stop and supervisor review. Never use an em dash."},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
        )
        answer = completion.choices[0].message.content.replace("—", ",").replace("–", "-")
        if not any(f"[{source}]" in answer for source, _ in found):
            answer = fallback
        return {"answer": answer, "sources": [s for s, _ in found], "mode": "groq"}
    except Exception:
        return {"answer": fallback, "sources": [s for s, _ in found], "mode": "offline"}


def motivation(operator_name: str, lesson_title: str) -> str:
    fallback = f"Good work, {operator_name}. You completed {lesson_title}. Apply one idea from it on your next task."
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return fallback
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        result = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"), temperature=0.5, max_tokens=60,
            messages=[{"role": "system", "content": "Write one brief, practical training encouragement. Never use an em dash."}, {"role": "user", "content": f"{operator_name} completed {lesson_title}."}],
        )
        return result.choices[0].message.content.replace("—", ",").replace("–", "-")
    except Exception:
        return fallback
