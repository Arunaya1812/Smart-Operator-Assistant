"""Small end-to-end API check. Uses a disposable database."""
from __future__ import annotations

import os
from pathlib import Path

SMOKE_DB = Path(__file__).resolve().parent / "data" / "smoke_test.db"
os.environ["SOA_DATABASE_PATH"] = str(SMOKE_DB)
if SMOKE_DB.exists():
    SMOKE_DB.unlink()

from fastapi.testclient import TestClient
from synthetic_data import generate

generate(days=30, noise=1.0, seed=7, reset=True)

from train_models import train
train(1.0)
from main import app

with TestClient(app) as client:
    assert client.get("/api/health").status_code == 200
    operators = client.get("/api/operators").json()
    assert len(operators) == 2
    dashboard = client.get("/api/dashboard/1").json()
    assert dashboard["machine"]["machine_type"] == "Backhoe Loader"
    assert dashboard["shift_start"].endswith("+05:30")
    assert dashboard["tasks"][0]["site_instruction"].startswith("SITE-101 north-east end")
    trainee_training = client.get("/api/training/1").json()
    assert len(trainee_training["lessons"]) == 2
    assert "recommended" in trainee_training["training_summary"].lower()
    assert trainee_training["lessons"][0]["video_url"].endswith("rgi-X9N1y38")
    assert trainee_training["lessons"][1]["video_url"].endswith("4p9cgqS_UjY")
    arjun_training = client.get("/api/training/2").json()
    assert len(arjun_training["lessons"]) == 2 and arjun_training["eligible"] is True
    excavator = client.get("/api/dashboard/2").json()
    assert excavator["breakdown"]["risk"] in {"elevated", "high"}
    questions = {
        "Hello": "Hello",
        "How many tasks do I have left today?": "left today",
        "My seatbelt broke in the middle of the task": "Report a defect",
        "Where do I navigate in the app to see complaints?": "Safety",
        "How to operate the loader controls?": "Training",
    }
    for question, expected in questions.items():
        response = client.post("/api/assistant/ask", json={"operator_id": 1, "question": question})
        assert response.status_code == 200 and expected in response.json()["answer"]
        if "seatbelt broke" in question:
            assert response.json()["automatic_actions"]["supervisor_contacted"] is True
    proximity = client.post("/api/assistant/ask", json={"operator_id": 1, "question": "There is a worker inside my swing radius"}).json()
    assert proximity["automatic_actions"]["supervisor_contacted"] is True
    assert "stop all movement" in proximity["answer"].lower()
    motivation = client.post("/api/assistant/ask", json={"operator_id": 1, "question": "I'm scared"}).json()
    assert motivation["mode"] == "motivation" and "okay" in motivation["answer"].lower()
    long_day = client.post("/api/assistant/ask", json={"operator_id": 2, "question": "Today was a long day"}).json()
    assert long_day["mode"] == "motivation" and "safely" in long_day["answer"].lower()
    unknown_answer = "I do not have information about that. Please connect with your supervisor"
    for inappropriate in ("Write me a romantic poem", "How to hurt someone", "You are stupid", "What color is the machine?", "Can I operate the machine underwater?"):
        response = client.post("/api/assistant/ask", json={"operator_id": 1, "question": inappropriate}).json()
        assert response["mode"] == "unknown" and response["answer"] == unknown_answer and response["sources"] == []
    manual_cases = {
        "How to dig a trench safely?": "1 m",
        "What is the excavator speed limit?": "4 km/h",
        "What if the boom contacts a power line?": "stay in the cab",
        "How should I shut down the machine?": "two minutes",
        "How is machine efficiency calculated?": "35 percent",
    }
    for question, expected in manual_cases.items():
        response = client.post("/api/assistant/ask", json={"operator_id": 1, "question": question}).json()
        assert expected.lower() in response["answer"].lower() and response["mode"] == "verified_local"
    pending = next(t for t in dashboard["tasks"] if t["status"] == "pending")
    failed = client.post(f"/api/tasks/{pending['id']}/start", json={"brakes": False, "fluids": True, "seatbelt": True, "work_area_clear": True, "cable_clearance": True})
    assert failed.status_code == 400
    passed = client.post(f"/api/tasks/{pending['id']}/start", json={"brakes": True, "fluids": True, "seatbelt": True, "work_area_clear": True, "cable_clearance": True})
    assert passed.status_code == 200
    detected = None
    for _ in range(60):
        detected = client.post(f"/api/tasks/{pending['id']}/sensor-scan").json().get("hazard")
        if detected:
            break
    assert detected and detected["auto_logged"] is True
    assert client.post(f"/api/tasks/{pending['id']}/complete", json={"simulated_minutes": pending["predicted_minutes"]}).status_code == 200
    incident = client.post("/api/incidents", json={"operator_id": 1, "machine_id": 1, "event_type": "drowsiness", "severity": "critical", "details": "Synthetic drowsiness threshold crossed"}).json()
    assert incident["authority_alerted"] is True
    ticket = client.post("/api/tickets", json={"operator_id": 1, "machine_id": 1, "incident_id": incident["id"], "component": "brakes", "description": "Brake response needs inspection"})
    assert ticket.status_code == 200
    answer = client.post("/api/assistant/ask", json={"operator_id": 1, "question": "What should I do if the engine overheats?"}).json()
    assert answer["answer"] and answer["sources"]
    assert client.get("/api/metrics/machines/1?period=week").status_code == 200
    assert len(client.get("/api/model-metrics").json()) == 3
    arjun_lesson = client.post("/api/training/2/lessons/1/complete").json()
    assert arjun_lesson["completed"] is True and arjun_lesson["promoted"] is False
    assert arjun_lesson["new_expertise"] == "experienced"
    assert client.post("/api/training/1/lessons/1/complete").status_code == 200
    promoted = client.post("/api/training/1/lessons/2/complete").json()
    assert promoted["promoted"] is True
    library = client.get("/api/training/1").json()
    assert library["library_mode"] is True and len(library["lessons"]) == 2
    assert all(lesson["completed"] for lesson in library["lessons"])

SMOKE_DB.unlink(missing_ok=True)
print("Smoke test passed")
