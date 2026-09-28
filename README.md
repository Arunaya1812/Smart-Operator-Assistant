# Smart Operator Assistant

A hackathon-ready, full-stack prototype for a CAT backhoe loader and mining excavator. The app runs entirely on generated data and has no real authentication, sensors, or external notifications.

## What is included

- React, Tailwind CSS, Lucide icons, Recharts, and browser speech APIs
- FastAPI with SQLite using a PostgreSQL-compatible relational schema
- 60 days of noisy synthetic tasks, weather, telemetry, incidents, and a component degradation curve
- Trained task-duration, breakdown-risk, and anomaly-detection models
- Chroma and `all-MiniLM-L6-v2` retrieval, with a lexical fallback if the model is unavailable
- A synthetic operator manual stored in `backend/manual.md`, with direct verified answers for common machine and safety questions
- Optional Groq answers and lesson encouragement, with offline-safe templated responses
- Server-authoritative pre-start checks, task transitions, points, lesson promotion, incident logging, and machine metrics
- Explicit IST display and `SITE-101 north-east end, 30 meter` work instructions for every task
- Probabilistic active-task sensor scans that interrupt with a hazard popup and auto-log the incident
- Five varied tasks per machine day, minute-level weather variation, seeded complaint examples, and simulated ticket progression
- Deterministic chatbot intents for greetings, live remaining-task counts, mid-task failures, app navigation, and training referrals
- Supportive responses for operator check-ins such as fear, nervousness, discouragement, or a long day
- Strict unknown-topic handling that returns a supervisor handoff instead of borrowing an unrelated safety passage
- Global hands-free assistance: opt in once, say `operator help`, and ask a question without opening the Assistant page
- Automatic incident, maintenance-ticket, and supervisor-workflow records for voice-reported critical hazards
- Independent chatbot voice playback control, natural spoken dates, a dark/light theme toggle, and sticky navigation
- Mistake- and hazard-driven lesson explanations, training access for every operator, the supplied YouTube videos, and a completed-lesson library that remains visible after completion
- CORS allow-list, request validation, parameterized SQL, transactions, security headers, and per-client rate limiting

No operator efficiency or productivity field exists. All efficiency data is calculated and stored per machine and day.

## Design documentation

- [System architecture](docs/system-architecture.md)
- [Application workflows](docs/workflow.md)
- [Entity-relationship diagram](docs/er-diagram.md)

## Run locally

Prerequisites: Python 3.11 or 3.12 and Node.js 20 or newer.

From the repository root, create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Generate a fresh dataset and train the models:

```powershell
python backend\synthetic_data.py --days 60 --noise 1.0 --seed 42
python backend\train_models.py --noise 1.0
```

The noise parameter accepts values from `0` to `3`. Sensor values and durations use Gaussian noise scaled by this setting.

Optionally build the persistent Chroma index. The first run downloads `all-MiniLM-L6-v2`:

```powershell
python backend\index_rag.py
```

Start the API:

```powershell
cd backend
uvicorn main:app --reload --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). API documentation is at [http://localhost:8000/api/docs](http://localhost:8000/api/docs).

## Groq configuration

Groq is optional. Copy `.env.example` to `.env`, set `GROQ_API_KEY`, and load it into the backend process. Never commit the key.

```powershell
$env:GROQ_API_KEY = "your-key"
$env:GROQ_MODEL = "llama-3.1-8b-instant"
```

Without the key, the assistant and motivation flow remain operational through grounded local fallbacks. Safety questions use verified manual responses before any LLM call. Other Groq responses must cite a retrieved local source or the backend replaces them with the grounded extractive fallback.

Browser voice input works best in Chrome or Edge and requires microphone permission. Turn on **Hands-free** in the header, then say `operator help` followed by the question, either in the same sentence or after the listener acknowledges the wake phrase. The typed question field uses the identical RAG pipeline. Voice playback selects an English or Indian English browser voice when available, normalizes numeric dates before speaking, and can be disabled on the Assistant page.

For this prototype, “contacting the supervisor” means creating a local escalation record. It does not call, message, or notify a real person.

## Current model metrics

The checked dataset uses 60 days, seed 42, and noise level 1.0.

| Model | Metric | Result |
| --- | --- | ---: |
| Task duration regression | MAE | 6.61 minutes |
| Task duration regression | RMSE | 8.40 minutes |
| Breakdown classification | Precision / recall | 0.984 / 0.984 |
| Hours-to-failure projection | MAE | 25.94 hours |
| Anomaly detection | Precision / recall | 0.765 / 1.000 |

Metrics are recalculated every time `train_models.py` runs and are stored in `backend/artifacts/metrics.json` and the `model_metrics` table. They are visible in the Machine metrics screen. The imperfect duration and anomaly precision are intentional consequences of sensor and duration noise. Breakdown labels remain highly separable because one excavator has an explicit gradual degradation curve.

## Efficiency formula

The daily machine score is transparent:

```text
35% task completion rate
+ 30% actual versus predicted time score
+ 20% idling score
+ 15% safety score
```

The backend recalculates the score after task completion and safety incidents. Weekly and monthly charts link to the stored daily inputs.

## Security and data integrity

- The frontend cannot directly update points, expertise, efficiency, incidents, or ticket status outside defined API operations.
- Pydantic validates lengths, numeric limits, and enum values.
- SQLite foreign keys, check constraints, write transactions, and WAL mode protect relational integrity.
- SQL statements are parameterized.
- CORS defaults to local development origins and can be narrowed through `ALLOWED_ORIGINS`.
- The API returns clickjacking, MIME-sniffing, referrer, and content-security headers.
- An in-memory rate limiter defaults to 120 requests per client per minute.
- Secrets are read only from environment variables and `.env` is ignored.

For production, replace the demo identity picker with real authentication, use Redis-backed distributed rate limiting, terminate TLS at a trusted proxy, rotate secrets, and move to managed PostgreSQL with encrypted backups.

## Verification

```powershell
python backend\smoke_test.py
cd frontend
npm run build
```

The smoke test uses a disposable database and checks pre-start enforcement, task completion, drowsiness response, ticket creation, manual-grounded assistant answers, critical voice escalation, Maya-only training assignment, completed-video access, metrics, and model reporting.
