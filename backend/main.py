from __future__ import annotations

import json
import os
import random
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db import DB_PATH, connect, init_db
from logic import breakdown_prediction, mistake_for_task, model_metrics, ordered_tasks, predict_duration, refresh_daily_metric
from rag_service import answer_question, motivation, rebuild_index

app = FastAPI(title="Smart Operator Assistant API", version="1.0.0", docs_url="/api/docs", redoc_url=None)
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])

request_log: dict[str, deque] = defaultdict(deque)


def now_ist() -> datetime:
    return datetime.now(IST)


def task_instruction(title: str) -> str:
    return f"SITE-101 north-east end. Complete 30 meter {title.lower()}."


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = request_log[client]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
    if len(bucket) >= limit:
        return JSONResponse({"detail": "Rate limit exceeded. Try again shortly."}, status_code=429)
    bucket.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


class StartTask(BaseModel):
    brakes: bool
    fluids: bool
    seatbelt: bool
    work_area_clear: bool
    cable_clearance: bool


class CompleteTask(BaseModel):
    simulated_minutes: float | None = Field(default=None, ge=5, le=480)


class SafetyEvent(BaseModel):
    operator_id: int = Field(gt=0)
    machine_id: int = Field(gt=0)
    task_id: int | None = Field(default=None, gt=0)
    event_type: Literal["seatbelt", "speed_limit", "rollover", "proximity", "drowsiness", "electrical_cable", "low_charge", "faulty_component"]
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    details: str = Field(min_length=3, max_length=300)


class TicketCreate(BaseModel):
    operator_id: int = Field(gt=0)
    machine_id: int = Field(gt=0)
    incident_id: int | None = Field(default=None, gt=0)
    component: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=5, max_length=500)


class TicketUpdate(BaseModel):
    status: Literal["open", "in progress", "resolved"]


class Question(BaseModel):
    operator_id: int = Field(gt=0)
    question: str = Field(min_length=3, max_length=500)


@app.on_event("startup")
def startup() -> None:
    if not DB_PATH.exists():
        from synthetic_data import generate
        generate(days=60, noise=1.0, seed=42)
    init_db()
    artifact = Path(__file__).resolve().parent / "artifacts" / "task_duration.joblib"
    if not artifact.exists():
        from train_models import train
        train(1.0)
    if os.getenv("REBUILD_RAG_ON_START", "0") == "1":
        rebuild_index()


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "connected", "groq_configured": bool(os.getenv("GROQ_API_KEY"))}


@app.get("/api/operators")
def operators():
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT id,name,expertise,points FROM operators ORDER BY id")]


@app.get("/api/dashboard/{operator_id}")
def dashboard(operator_id: int):
    today = now_ist().date().isoformat()
    with connect() as conn:
        operator = conn.execute("SELECT * FROM operators WHERE id=?", (operator_id,)).fetchone()
        if not operator:
            raise HTTPException(404, "Operator not found")
        task_rows = conn.execute("""SELECT t.*,m.machine_code,m.machine_type,m.age_years FROM tasks t
            JOIN machines m ON m.id=t.machine_id WHERE t.operator_id=? AND t.day=?""", (operator_id, today)).fetchall()
        if not task_rows:
            task_rows = conn.execute("""SELECT t.*,m.machine_code,m.machine_type,m.age_years FROM tasks t
                JOIN machines m ON m.id=t.machine_id WHERE t.operator_id=? ORDER BY t.day DESC LIMIT 3""", (operator_id,)).fetchall()
        weather = conn.execute("SELECT * FROM weather_daily WHERE day=?", (today,)).fetchone()
        incidents = conn.execute("SELECT * FROM incidents WHERE operator_id=? ORDER BY created_at DESC LIMIT 8", (operator_id,)).fetchall()
    tasks = [dict(r) for r in task_rows]
    weather_data = dict(weather) if weather else None
    if weather_data:
        # Stable within a minute, then changes slightly to resemble a live site station.
        minute_bucket = int(now_ist().timestamp() // 60)
        live_rng = random.Random(minute_bucket + operator_id * 997)
        weather_data["temperature_c"] = round(weather_data["temperature_c"] + live_rng.uniform(-1.4, 1.4), 1)
        weather_data["wind_kph"] = round(max(0, weather_data["wind_kph"] + live_rng.uniform(-3.0, 3.0)), 1)
        weather_data["precipitation_mm"] = round(max(0, weather_data["precipitation_mm"] + live_rng.uniform(-0.8, 0.8)), 1)
        if live_rng.random() < 0.12:
            weather_data["condition"] = live_rng.choice(["clear", "cloudy", "light rain", "hot"])
    for task in tasks:
        task["site_instruction"] = task_instruction(task["title"])
        if weather_data:
            task["predicted_minutes"] = predict_duration(task["machine_type"], task["age_years"], weather_data["condition"], task["planned_start_hour"])
    machine = None
    risk = None
    if tasks:
        machine = {k: tasks[0][k] for k in ("machine_id", "machine_code", "machine_type", "age_years")}
        risk = breakdown_prediction(machine["machine_id"])
    return {"operator": dict(operator), "machine": machine, "weather": weather_data,
            "tasks": ordered_tasks(tasks), "breakdown": risk, "recent_incidents": [dict(x) for x in incidents], "shift_start": f"{today}T07:00:00+05:30"}


@app.post("/api/tasks/{task_id}/start")
def start_task(task_id: int, checks: StartTask):
    if not all(checks.model_dump().values()):
        raise HTTPException(400, "Every pre-start check must pass before the task can start")
    with connect() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found")
        if task["status"] == "completed":
            raise HTTPException(409, "Task is already completed")
        if task["prerequisite_id"]:
            prerequisite = conn.execute("SELECT status FROM tasks WHERE id=?", (task["prerequisite_id"],)).fetchone()
            if prerequisite and prerequisite[0] != "completed":
                raise HTTPException(409, "Complete the prerequisite task first")
        conn.execute("UPDATE tasks SET status='in_progress',started_at=? WHERE id=?", (now_ist().isoformat(), task_id))
    return {"status": "in_progress", "instruction": f"{task_instruction(task['title'])} Confirm the area is clear. Use smooth controls and stop if a warning appears."}


@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int, payload: CompleteTask):
    now = now_ist().isoformat()
    with connect() as conn:
        task = conn.execute("SELECT t.*,o.expertise FROM tasks t JOIN operators o ON o.id=t.operator_id WHERE t.id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found")
        if task["status"] != "in_progress":
            raise HTTPException(409, "Start the task before completing it")
        minutes = payload.simulated_minutes if payload.simulated_minutes is not None else task["predicted_minutes"]
        minutes = max(5, min(480, float(minutes)))
        conn.execute("UPDATE tasks SET status='completed',actual_minutes=?,completed_at=? WHERE id=?", (minutes, now, task_id))
        conn.execute("UPDATE operators SET points=points+? WHERE id=?", (task["points"], task["operator_id"]))
    refresh_daily_metric(task["machine_id"], task["day"])
    mistake = mistake_for_task(task_id) if task["expertise"] == "trainee" else None
    lesson = {"harsh_unsafe": "safety", "operational_error": "how_to"}.get(mistake)
    return {"status": "completed", "points_awarded": task["points"], "actual_minutes": minutes, "mistake_type": mistake, "recommended_lesson": lesson}


@app.get("/api/training/{operator_id}")
def training(operator_id: int):
    with connect() as conn:
        op = conn.execute("SELECT * FROM operators WHERE id=?", (operator_id,)).fetchone()
        if not op: raise HTTPException(404, "Operator not found")
        all_lessons = conn.execute("""SELECT l.*,CASE WHEN ol.completed_at IS NULL THEN 0 ELSE 1 END completed
            FROM lessons l LEFT JOIN operator_lessons ol ON ol.lesson_id=l.id AND ol.operator_id=? ORDER BY l.id""", (operator_id,)).fetchall()
        mistakes = conn.execute("""SELECT anomaly_label,COUNT(*) count FROM telemetry
            WHERE operator_id=? AND anomaly_label IS NOT NULL GROUP BY anomaly_label""", (operator_id,)).fetchall()
        hazards = conn.execute("""SELECT event_type,COUNT(*) count FROM incidents
            WHERE operator_id=? GROUP BY event_type ORDER BY count DESC""", (operator_id,)).fetchall()
    mistake_counts = {row["anomaly_label"]: row["count"] for row in mistakes}
    hazard_counts = {row["event_type"]: row["count"] for row in hazards}
    hazard_labels = {"seatbelt": "seatbelt", "speed_limit": "speed-limit", "rollover": "rollover",
        "proximity": "proximity", "drowsiness": "drowsiness", "electrical_cable": "electrical-cable",
        "low_charge": "low-charge", "faulty_component": "component-fault", "voice_critical_hazard": "voice-reported critical"}
    logged_hazards = ", ".join(f"{hazard_labels.get(name, name.replace('_','-'))} ({count})" for name, count in hazard_counts.items())
    safety_count = mistake_counts.get("harsh_unsafe", 0)
    operation_count = mistake_counts.get("operational_error", 0)
    summary_parts = []
    if safety_count:
        detail = f" Logged hazard types: {logged_hazards}." if logged_hazards else ""
        summary_parts.append(f"You had {safety_count} harsh or unsafe telemetry events.{detail} Safety hazards is recommended")
    if operation_count:
        summary_parts.append(f"You had {operation_count} operational sequence or load events. How to use the machine is recommended")
    training_summary = ". ".join(summary_parts) + ("." if summary_parts else "No mistake-linked lesson is currently required.")
    lessons = []
    for row in all_lessons:
        lesson = dict(row)
        category = "harsh_unsafe" if lesson["lesson_type"] == "safety" else "operational_error"
        lesson["mistake_count"] = mistake_counts.get(category, 0)
        lesson["recommended"] = lesson["mistake_count"] > 0
        if lesson["recommended"]:
            if category == "harsh_unsafe":
                lesson["recommendation_reason"] = f"{lesson['mistake_count']} harsh or unsafe events were detected" + (f", including {logged_hazards}" if logged_hazards else "") + f". {lesson['title']} is recommended"
            else:
                lesson["recommendation_reason"] = f"{lesson['mistake_count']} operational sequence or load events were detected. {lesson['title']} is recommended"
        else:
            lesson["recommendation_reason"] = None
        lessons.append(lesson)
    all_completed = bool(lessons) and all(bool(lesson["completed"]) for lesson in lessons)
    return {"eligible": True, "expertise": op["expertise"], "lessons": lessons,
            "mistake_summary": mistake_counts, "hazard_summary": hazard_counts, "training_summary": training_summary,
            "library_mode": all_completed}


@app.post("/api/training/{operator_id}/lessons/{lesson_id}/complete")
def complete_lesson(operator_id: int, lesson_id: int):
    now = now_ist().isoformat()
    with connect() as conn:
        op = conn.execute("SELECT * FROM operators WHERE id=?", (operator_id,)).fetchone()
        lesson = conn.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        if not op or not lesson: raise HTTPException(404, "Operator or lesson not found")
        conn.execute("INSERT OR IGNORE INTO operator_lessons VALUES(?,?,?)", (operator_id, lesson_id, now))
        count = conn.execute("SELECT COUNT(*) FROM operator_lessons WHERE operator_id=?", (operator_id,)).fetchone()[0]
        promoted = op["expertise"] == "trainee" and count >= 2
        if promoted: conn.execute("UPDATE operators SET expertise='beginner' WHERE id=?", (operator_id,))
    return {"completed": True, "promoted": promoted, "new_expertise": "beginner" if promoted else op["expertise"], "message": motivation(op["name"], lesson["title"])}


@app.post("/api/incidents")
def log_incident(event: SafetyEvent):
    now = now_ist().isoformat()
    authority = event.event_type == "drowsiness"
    action = "Vehicle slowed and stopped. Audible alert triggered. Site authority log created." if authority else "Operator warning displayed and event logged."
    with connect() as conn:
        machine = conn.execute("SELECT id FROM machines WHERE id=?", (event.machine_id,)).fetchone()
        operator = conn.execute("SELECT id FROM operators WHERE id=?", (event.operator_id,)).fetchone()
        if not machine or not operator: raise HTTPException(404, "Machine or operator not found")
        cur = conn.execute("""INSERT INTO incidents(created_at,machine_id,operator_id,task_id,event_type,severity,message,authority_alerted,auto_action)
            VALUES(?,?,?,?,?,?,?,?,?)""", (now,event.machine_id,event.operator_id,event.task_id,event.event_type,event.severity,event.details,int(authority),action))
        incident_id = cur.lastrowid
    refresh_daily_metric(event.machine_id, now_ist().date().isoformat())
    return {"id": incident_id, "logged": True, "authority_alerted": authority, "auto_action": action}


@app.post("/api/tasks/{task_id}/sensor-scan")
def sensor_scan(task_id: int):
    """Prototype sensor scan. Hazards are probabilistic, but telemetry changes their weights."""
    with connect() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found")
        if task["status"] != "in_progress":
            raise HTTPException(409, "Sensor monitoring requires an active task")
        sample = conn.execute("""SELECT speed_kph,vibration,temperature_c,load_pct,harsh_swing,
            proximity_m,seatbelt,drowsiness,component_health FROM telemetry
            WHERE task_id=? ORDER BY RANDOM() LIMIT 1""", (task_id,)).fetchone()
        if not sample:
            raise HTTPException(404, "No telemetry available for this task")

        # A scan does not always produce an alert. This keeps the intervention unexpected.
        scan_probability = random.uniform(0.22, 0.38)
        if random.random() > scan_probability:
            return {"hazard": None, "scan_probability": round(scan_probability, 3)}

        candidates = [
            ("seatbelt", 4.0 if not sample[6] else 0.8, "Seatbelt latch signal was lost", "high", "Stop motion until the restraint is secured."),
            ("speed_limit", 3.5 if sample[0] > 15 else 1.0, f"Speed reached {sample[0]:.1f} km/h", "medium", "Travel speed reduced automatically."),
            ("rollover", 3.2 if sample[3] > 82 and sample[4] > 0.8 else 0.7, "Load and swing pattern raised rollover risk", "high", "Hydraulic motion limited. Reposition on stable ground."),
            ("proximity", 4.2 if sample[5] < 2.0 else 1.0, f"Object detected {sample[5]:.1f} meters inside the blind spot", "critical", "Machine stopped. Confirm the exclusion zone is clear."),
            ("drowsiness", 4.0 if sample[7] > 0.52 else 0.6, f"Drowsiness signal reached {sample[7]:.2f}", "critical", "Vehicle slowed and stopped. Site authority log created."),
            ("electrical_cable", 0.9, "Boom path is approaching the electrical cable clearance limit", "high", "Boom movement stopped. Recheck cable clearance."),
            ("low_charge", 2.5 if sample[8] < 0.48 else 0.6, f"Component charge health fell to {sample[8]*100:.0f}%", "medium", "Nonessential load reduced. Maintenance review requested."),
            ("faulty_component", 3.8 if sample[1] > 5.5 or sample[2] > 94 else 0.9, f"Vibration {sample[1]:.1f} and temperature {sample[2]:.0f} C are outside trend", "high", "Load limited. Inspect the component before continuing."),
        ]
        chosen = random.choices(candidates, weights=[x[1] for x in candidates], k=1)[0]
        event_type, _, message, severity, action = chosen
        duplicate = conn.execute("SELECT id FROM incidents WHERE task_id=? AND event_type=?", (task_id, event_type)).fetchone()
        if duplicate:
            return {"hazard": None, "scan_probability": round(scan_probability, 3)}
        confidence = random.randint(72, 97)
        authority = event_type == "drowsiness"
        cur = conn.execute("""INSERT INTO incidents(created_at,machine_id,operator_id,task_id,event_type,severity,message,authority_alerted,auto_action)
            VALUES(?,?,?,?,?,?,?,?,?)""", (now_ist().isoformat(), task["machine_id"], task["operator_id"], task_id,
            event_type, severity, message, int(authority), action))
    refresh_daily_metric(task["machine_id"], task["day"])
    return {"hazard": {"id": cur.lastrowid, "event_type": event_type, "severity": severity,
        "message": message, "action": action, "confidence": confidence, "auto_logged": True},
        "scan_probability": round(scan_probability, 3)}


@app.get("/api/incidents")
def incidents(operator_id: int | None = None):
    with connect() as conn:
        if operator_id:
            rows = conn.execute("SELECT * FROM incidents WHERE operator_id=? ORDER BY created_at DESC LIMIT 100", (operator_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM incidents ORDER BY created_at DESC LIMIT 100").fetchall()
    return [dict(x) for x in rows]


@app.post("/api/tickets")
def create_ticket(ticket: TicketCreate):
    with connect() as conn:
        cur = conn.execute("""INSERT INTO tickets(created_at,machine_id,operator_id,incident_id,component,description,status)
            VALUES(?,?,?,?,?,?,'open')""", (now_ist().isoformat(), ticket.machine_id, ticket.operator_id, ticket.incident_id, ticket.component, ticket.description))
    return {"id": cur.lastrowid, "status": "open"}


@app.get("/api/tickets")
def tickets(operator_id: int | None = None):
    with connect() as conn:
        # Prototype workflow progression. Refreshing may advance a complaint, never move it backward.
        active = conn.execute("SELECT id,status FROM tickets WHERE status!='resolved'").fetchall()
        for ticket in active:
            chance = random.random()
            if ticket["status"] == "open" and chance < 0.18:
                conn.execute("UPDATE tickets SET status='in progress' WHERE id=?", (ticket["id"],))
            elif ticket["status"] == "in progress" and chance < 0.08:
                conn.execute("UPDATE tickets SET status='resolved' WHERE id=?", (ticket["id"],))
        if operator_id:
            rows = conn.execute("SELECT * FROM tickets WHERE operator_id=? ORDER BY created_at DESC", (operator_id,)).fetchall()
        else: rows = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC").fetchall()
    return [dict(x) for x in rows]


@app.patch("/api/tickets/{ticket_id}")
def update_ticket(ticket_id: int, payload: TicketUpdate):
    with connect() as conn:
        cur = conn.execute("UPDATE tickets SET status=? WHERE id=?", (payload.status, ticket_id))
        if cur.rowcount == 0: raise HTTPException(404, "Ticket not found")
    return {"id": ticket_id, "status": payload.status}


@app.get("/api/metrics/machines/{machine_id}")
def machine_metrics(machine_id: int, period: Literal["week", "month"] = "week"):
    limit = 7 if period == "week" else 30
    with connect() as conn:
        rows = conn.execute("SELECT * FROM daily_metrics WHERE machine_id=? ORDER BY day DESC LIMIT ?", (machine_id, limit)).fetchall()
    return {"period": period, "formula": "35% completion + 30% time + 20% idle + 15% safety", "days": [dict(x) for x in reversed(rows)]}


@app.get("/api/model-metrics")
def metrics():
    return model_metrics()


@app.post("/api/assistant/ask")
def ask(payload: Question):
    with connect() as conn:
        if not conn.execute("SELECT id FROM operators WHERE id=?", (payload.operator_id,)).fetchone(): raise HTTPException(404, "Operator not found")
    result = answer_question(payload.question, payload.operator_id)
    if result.get("critical_safety"):
        created_at = now_ist().isoformat()
        with connect() as conn:
            assignment = conn.execute("""SELECT machine_id,id task_id,day FROM tasks WHERE operator_id=?
                ORDER BY CASE WHEN status='in_progress' THEN 0 ELSE 1 END, day DESC, planned_start_hour DESC LIMIT 1""", (payload.operator_id,)).fetchone()
            if assignment:
                incident = conn.execute("""INSERT INTO incidents(created_at,machine_id,operator_id,task_id,event_type,severity,message,authority_alerted,auto_action)
                    VALUES(?,?,?,?,?,'critical',?,1,?)""", (created_at, assignment["machine_id"], payload.operator_id,
                    assignment["task_id"], "voice_critical_hazard", payload.question,
                    "Machine stop advised. Supervisor escalation and maintenance ticket created."))
                ticket = conn.execute("""INSERT INTO tickets(created_at,machine_id,operator_id,incident_id,component,description,status)
                    VALUES(?,?,?,?,?,?,'open')""", (created_at, assignment["machine_id"], payload.operator_id,
                    incident.lastrowid, result.get("component", "safety component"),
                    f"Voice-reported critical hazard: {payload.question}"))
                escalation = conn.execute("INSERT INTO escalations(created_at,operator_id,question,status) VALUES(?,?,?,'logged')",
                    (created_at, payload.operator_id, payload.question))
                result["automatic_actions"] = {"supervisor_contacted": True, "incident_id": incident.lastrowid,
                    "ticket_id": ticket.lastrowid, "escalation_id": escalation.lastrowid}
                result["answer"] += " I have logged the incident, opened the maintenance ticket, and contacted the supervisor workflow."
        if assignment:
            refresh_daily_metric(assignment["machine_id"], assignment["day"])
    return result


@app.post("/api/assistant/escalate")
def escalate(payload: Question):
    with connect() as conn:
        cur = conn.execute("INSERT INTO escalations(created_at,operator_id,question,status) VALUES(?,?,?,'logged')", (now_ist().isoformat(), payload.operator_id, payload.question))
    return {"id": cur.lastrowid, "status": "logged", "message": "Supervisor handoff logged for site review."}
