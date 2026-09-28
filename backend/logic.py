from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np

from db import connect
from synthetic_data import compute_efficiency

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"


def ordered_tasks(rows: list[dict]) -> list[dict]:
    """Kahn topological sort, choosing highest priority among available tasks."""
    by_id = {r["id"]: r for r in rows}
    indegree = {r["id"]: 0 for r in rows}
    children = defaultdict(list)
    for row in rows:
        prerequisite = row.get("prerequisite_id")
        if prerequisite in by_id:
            indegree[row["id"]] += 1
            children[prerequisite].append(row["id"])
    ready = [item for item in rows if indegree[item["id"]] == 0]
    result = []
    while ready:
        ready.sort(key=lambda x: (-x["priority"], x["planned_start_hour"]))
        item = ready.pop(0)
        result.append(item)
        for child in children[item["id"]]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(by_id[child])
    return result


def predict_duration(machine_type: str, age: float, weather: str, hour: int) -> float:
    path = ARTIFACT_DIR / "task_duration.joblib"
    if path.exists():
        model = joblib.load(path)
        return round(float(model.predict(np.array([[hour, machine_type, age, weather]], dtype=object))[0]), 1)
    weather_factor = {"clear": 1, "cloudy": 1.03, "light rain": 1.14, "heavy rain": 1.32, "hot": 1.1}.get(weather, 1.0)
    return round((22 if machine_type == "Backhoe Loader" else 34) * (1 + age * 0.025) * weather_factor * (1.08 if hour < 8 else 1), 1)


def breakdown_prediction(machine_id: int) -> dict:
    with connect() as conn:
        rows = conn.execute("""SELECT vibration,temperature_c,load_pct,component_health,recorded_at
            FROM telemetry WHERE machine_id=? ORDER BY recorded_at DESC LIMIT 12""", (machine_id,)).fetchall()
    if not rows:
        return {"probability": 0, "risk": "low", "hours_to_failure": None, "drivers": []}
    latest = np.array([[rows[0][0], rows[0][1], rows[0][2], rows[0][3]]], dtype=float)
    path = ARTIFACT_DIR / "breakdown.joblib"
    probability = float(joblib.load(path).predict_proba(latest)[0, 1]) if path.exists() else max(0, min(1, 1 - latest[0, 3]))
    health = float(np.mean([r[3] for r in rows[:4]]))
    vibration = float(np.mean([r[0] for r in rows[:4]]))
    temperature = float(np.mean([r[1] for r in rows[:4]]))
    hours = max(0, round((health - 0.28) * 220, 1))
    drivers = []
    if health < 0.55: drivers.append("component health decline")
    if vibration > 5.5: drivers.append("rising vibration")
    if temperature > 94: drivers.append("high temperature")
    risk = "high" if probability >= 0.65 or hours < 24 else "elevated" if probability >= 0.35 or hours < 60 else "low"
    return {"probability": round(probability, 3), "risk": risk, "hours_to_failure": hours, "drivers": drivers or ["normal operating range"]}


def refresh_daily_metric(machine_id: int, day: str) -> None:
    with connect() as conn:
        tasks = conn.execute("SELECT status,predicted_minutes,COALESCE(actual_minutes,0) actual_minutes FROM tasks WHERE machine_id=? AND day=?", (machine_id, day)).fetchall()
        if not tasks:
            return
        completed = sum(r[0] == "completed" for r in tasks)
        predicted = sum(r[1] for r in tasks if r[0] == "completed")
        actual = sum(r[2] for r in tasks if r[0] == "completed")
        idle = conn.execute("SELECT COALESCE(SUM(idle_minutes),0) FROM telemetry WHERE machine_id=? AND date(recorded_at)=?", (machine_id, day)).fetchone()[0]
        incidents = conn.execute("SELECT COUNT(*) FROM incidents WHERE machine_id=? AND date(created_at)=?", (machine_id, day)).fetchone()[0]
        s = compute_efficiency(completed, len(tasks), actual, predicted, idle, incidents)
        conn.execute("""INSERT OR REPLACE INTO daily_metrics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (day, machine_id,
            s["completion_rate"], s["time_score"], s["idle_score"], s["safety_score"], s["efficiency"],
            completed, len(tasks), actual, predicted, idle, incidents))


def mistake_for_task(task_id: int) -> str | None:
    with connect() as conn:
        rows = conn.execute("SELECT harsh_swing,proximity_m,seatbelt,temperature_c,load_pct,anomaly_label FROM telemetry WHERE task_id=?", (task_id,)).fetchall()
    if any(r[0] > 1.0 or r[1] < 1.4 or not r[2] or r[5] == "harsh_unsafe" for r in rows):
        return "harsh_unsafe"
    if any(r[3] > 98 or r[4] > 92 or r[5] == "operational_error" for r in rows):
        return "operational_error"
    return None


def model_metrics() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM model_metrics ORDER BY model_name").fetchall()
    return [{"model_name": r[0], "metrics": json.loads(r[1]), "trained_at": r[2], "noise_level": r[3]} for r in rows]
