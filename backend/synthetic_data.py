from __future__ import annotations

import argparse
import json
import math
import random
from datetime import date, datetime, timedelta

import numpy as np

from db import DB_PATH, connect, init_db

MACHINE_TYPES = {1: "Backhoe Loader", 2: "Mining Excavator"}
WEATHER = ["clear", "cloudy", "light rain", "heavy rain", "hot"]
TASKS = {
    "Backhoe Loader": [
        ("Pre-start inspection", "inspection", 100),
        ("Excavate utility trench", "excavation", 80),
        ("Load excavated spoil", "loading", 72),
        ("Backfill utility trench", "backfill", 64),
        ("Final surface grading", "grading", 56),
    ],
    "Mining Excavator": [
        ("Pre-start inspection", "inspection", 100),
        ("Prepare bench face", "preparation", 88),
        ("Load haul trucks", "loading", 80),
        ("Bench face cleanup", "cleanup", 65),
        ("Shutdown inspection", "inspection", 55),
    ],
}


def duration_formula(machine_type: str, age: float, weather: str, hour: int, noise: float, rng: np.random.Generator) -> float:
    base = 22 if machine_type == "Backhoe Loader" else 34
    weather_factor = {"clear": 1.0, "cloudy": 1.03, "light rain": 1.14, "heavy rain": 1.32, "hot": 1.1}[weather]
    time_factor = 1.08 if hour < 8 else 1.06 if hour >= 16 else 1.0
    value = base * (1 + age * 0.025) * weather_factor * time_factor
    return max(8.0, float(value + rng.normal(0, noise * 7)))


def compute_efficiency(completed: int, total: int, actual: float, predicted: float, idle: float, incidents: int) -> dict:
    completion_rate = completed / total if total else 0
    time_score = min(1.0, predicted / actual) if actual > 0 else 0
    idle_score = max(0.0, 1 - idle / max(actual, 1))
    safety_score = max(0.0, 1 - incidents * 0.12)
    efficiency = 100 * (0.35 * completion_rate + 0.30 * time_score + 0.20 * idle_score + 0.15 * safety_score)
    return {
        "completion_rate": completion_rate,
        "time_score": time_score,
        "idle_score": idle_score,
        "safety_score": safety_score,
        "efficiency": max(0, min(100, efficiency)),
    }


def generate(days: int = 60, noise: float = 1.0, seed: int = 42, reset: bool = True) -> None:
    if not 30 <= days <= 90:
        raise ValueError("days must be between 30 and 90")
    if not 0 <= noise <= 3:
        raise ValueError("noise must be between 0 and 3")
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    rng = np.random.default_rng(seed)
    random.seed(seed)
    today = date.today()
    start = today - timedelta(days=days - 1)
    with connect() as conn:
        conn.executemany("INSERT INTO operators(id,name,expertise,points) VALUES(?,?,?,?)", [
            (1, "Maya Singh", "trainee", 140),
            (2, "Arjun Rao", "experienced", 520),
        ])
        conn.executemany("INSERT INTO machines(id,machine_code,machine_type,age_years,service_hours,last_service_hours) VALUES(?,?,?,?,?,?)", [
            (1, "CAT-BHL-07", "Backhoe Loader", 3.5, 2840, 2660),
            (2, "CAT-EXC-22", "Mining Excavator", 6.0, 7920, 7440),
        ])
        conn.executemany("INSERT INTO lessons(id,lesson_type,title,narration,video_url) VALUES(?,?,?,?,?)", [
            (1, "how_to", "How to use the machine", "Confirm the work area is clear. Start at low idle, engage controls in the approved sequence, and use smooth inputs. Stop and reset if the machine stalls.", "https://www.youtube.com/embed/rgi-X9N1y38"),
            (2, "safety", "Safety hazards", "Wear the seatbelt, check blind spots, respect the site speed limit, and keep clear of personnel and electrical cables. Stop work when conditions are unsafe.", "https://www.youtube.com/embed/4p9cgqS_UjY"),
        ])

        task_id = 1
        telemetry_id = 1
        incident_id = 1
        for offset in range(days):
            day = start + timedelta(days=offset)
            condition = random.choices(WEATHER, [42, 20, 17, 6, 15])[0]
            temp_base = {"clear": 28, "cloudy": 25, "light rain": 23, "heavy rain": 21, "hot": 38}[condition]
            temp = temp_base + rng.normal(0, 1.8 * noise)
            wind = max(2, 12 + rng.normal(0, 4 * noise))
            precip = max(0, ({"light rain": 4, "heavy rain": 15}.get(condition, 0)) + rng.normal(0, 1.5 * noise))
            conn.execute("INSERT INTO weather_daily VALUES(?,?,?,?,?)", (day.isoformat(), condition, temp, wind, precip))

            for machine_id, machine_type in MACHINE_TYPES.items():
                operator_id = 1 if machine_id == 1 else 2
                age = 3.5 if machine_id == 1 else 6.0
                degradation = 0.10 + (offset / max(1, days - 1)) * (0.18 if machine_id == 1 else 0.58)
                day_tasks = []
                previous = None
                for index, (title, task_type, priority) in enumerate(TASKS[machine_type]):
                    hour = 7 + index * 3
                    predicted = duration_formula(machine_type, age, condition, hour, noise, rng)
                    is_today = day == today
                    completed = not is_today or index == 0
                    status = "completed" if completed else "pending"
                    actual = predicted * max(0.72, 1 + rng.normal(0.04, 0.11 * noise)) if completed else None
                    completed_at = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=45).isoformat() if completed else None
                    conn.execute("""INSERT INTO tasks(id,day,operator_id,machine_id,title,task_type,priority,prerequisite_id,status,planned_start_hour,predicted_minutes,actual_minutes,points,started_at,completed_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (task_id, day.isoformat(), operator_id, machine_id, title, task_type, priority, previous, status, hour, predicted, actual, 20, completed_at, completed_at))
                    day_tasks.append((task_id, predicted, actual or 0, status))
                    previous = task_id

                    for sample in range(4):
                        ts = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=sample * 10)
                        component_health = max(0.08, 1 - degradation + rng.normal(0, 0.025 * noise))
                        vibration = 2.4 + degradation * 5.3 + rng.normal(0, 0.28 * noise)
                        engine_temp = 76 + degradation * 31 + rng.normal(0, 2.2 * noise)
                        load = 55 + index * 9 + rng.normal(0, 7 * noise)
                        harsh = max(0, rng.normal(0.25 + (0.45 if operator_id == 1 else 0.08), 0.28 * noise))
                        proximity = max(0.3, rng.normal(4.2, 1.6 * noise))
                        seatbelt = 0 if rng.random() < (0.06 if operator_id == 1 else 0.015) else 1
                        drowsiness = max(0, min(1, rng.normal(0.25 + (0.18 if hour >= 16 else 0), 0.12 * noise)))
                        speed = max(0, rng.normal(11 + load / 20, 2.4 * noise))
                        idle = max(0, rng.normal(3.0, 1.2 * noise))
                        label = None
                        if harsh > 1.0 or proximity < 1.4 or not seatbelt:
                            label = "harsh_unsafe"
                        elif engine_temp > 98 or load > 92:
                            label = "operational_error"
                        conn.execute("""INSERT INTO telemetry VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                            telemetry_id, ts.isoformat(), machine_id, operator_id, task_id, speed, vibration,
                            engine_temp, load, idle, harsh, proximity, seatbelt, drowsiness, component_health, label))
                        telemetry_id += 1
                    task_id += 1

                completed_n = sum(1 for _, _, _, s in day_tasks if s == "completed")
                predicted_total = sum(x[1] for x in day_tasks if x[3] == "completed")
                actual_total = sum(x[2] for x in day_tasks if x[3] == "completed")
                idle_total = conn.execute("SELECT COALESCE(SUM(idle_minutes),0) FROM telemetry WHERE machine_id=? AND date(recorded_at)=?", (machine_id, day.isoformat())).fetchone()[0]
                incidents = 0
                if rng.random() < 0.18 and not (day == today):
                    incidents = 1
                    conn.execute("INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?,?,?)", (incident_id, datetime.combine(day, datetime.min.time()).replace(hour=12).isoformat(), machine_id, operator_id, None, "speed_limit", "medium", "Synthetic speed limit violation", 0, "Speed reduced"))
                    incident_id += 1
                scores = compute_efficiency(completed_n, len(day_tasks), actual_total, predicted_total, idle_total, incidents)
                conn.execute("""INSERT INTO daily_metrics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    day.isoformat(), machine_id, scores["completion_rate"], scores["time_score"], scores["idle_score"],
                    scores["safety_score"], scores["efficiency"], completed_n, len(day_tasks), actual_total, predicted_total, idle_total, incidents))

        sample_tickets = [
            (datetime.combine(today - timedelta(days=2), datetime.min.time()).replace(hour=15).isoformat(), 1, 1, "Hydraulic hose", "Minor seepage near the loader arm coupling", "in progress"),
            (datetime.combine(today - timedelta(days=8), datetime.min.time()).replace(hour=11).isoformat(), 1, 1, "Reverse alarm", "Intermittent alarm during the pre-start test", "resolved"),
            (datetime.combine(today - timedelta(days=1), datetime.min.time()).replace(hour=16).isoformat(), 2, 2, "Swing bearing", "Vibration trend needs maintenance inspection", "open"),
        ]
        conn.executemany("""INSERT INTO tickets(created_at,machine_id,operator_id,incident_id,component,description,status)
            VALUES(?,?,?,NULL,?,?,?)""", sample_tickets)
    print(json.dumps({"database": str(DB_PATH), "days": days, "noise": noise, "seed": seed}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate noisy synthetic operator assistant data")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--noise", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-reset", action="store_true")
    args = parser.parse_args()
    generate(args.days, args.noise, args.seed, not args.no_reset)
