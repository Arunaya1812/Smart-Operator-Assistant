from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("SOA_DATABASE_PATH", DATA_DIR / "operator_assistant.db"))


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS operators (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, expertise TEXT NOT NULL
    CHECK (expertise IN ('trainee','beginner','experienced')),
  points INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS machines (
  id INTEGER PRIMARY KEY, machine_code TEXT UNIQUE NOT NULL, machine_type TEXT NOT NULL,
  age_years REAL NOT NULL, service_hours REAL NOT NULL, last_service_hours REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS weather_daily (
  day TEXT PRIMARY KEY, condition TEXT NOT NULL, temperature_c REAL NOT NULL,
  wind_kph REAL NOT NULL, precipitation_mm REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY, day TEXT NOT NULL, operator_id INTEGER NOT NULL REFERENCES operators(id),
  machine_id INTEGER NOT NULL REFERENCES machines(id), title TEXT NOT NULL, task_type TEXT NOT NULL,
  priority INTEGER NOT NULL, prerequisite_id INTEGER REFERENCES tasks(id), status TEXT NOT NULL,
  planned_start_hour INTEGER NOT NULL, predicted_minutes REAL NOT NULL,
  actual_minutes REAL, points INTEGER NOT NULL DEFAULT 20, started_at TEXT, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS telemetry (
  id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL, machine_id INTEGER NOT NULL REFERENCES machines(id),
  operator_id INTEGER REFERENCES operators(id), task_id INTEGER REFERENCES tasks(id),
  speed_kph REAL NOT NULL, vibration REAL NOT NULL, temperature_c REAL NOT NULL,
  load_pct REAL NOT NULL, idle_minutes REAL NOT NULL, harsh_swing REAL NOT NULL,
  proximity_m REAL NOT NULL, seatbelt INTEGER NOT NULL, drowsiness REAL NOT NULL,
  component_health REAL NOT NULL, anomaly_label TEXT
);
CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, machine_id INTEGER NOT NULL REFERENCES machines(id),
  operator_id INTEGER REFERENCES operators(id), task_id INTEGER REFERENCES tasks(id),
  event_type TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL,
  authority_alerted INTEGER NOT NULL DEFAULT 0, auto_action TEXT
);
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, machine_id INTEGER NOT NULL REFERENCES machines(id),
  operator_id INTEGER NOT NULL REFERENCES operators(id), incident_id INTEGER REFERENCES incidents(id),
  component TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open','in progress','resolved'))
);
CREATE TABLE IF NOT EXISTS lessons (
  id INTEGER PRIMARY KEY, lesson_type TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
  narration TEXT NOT NULL, video_url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operator_lessons (
  operator_id INTEGER NOT NULL REFERENCES operators(id), lesson_id INTEGER NOT NULL REFERENCES lessons(id),
  completed_at TEXT NOT NULL, PRIMARY KEY(operator_id, lesson_id)
);
CREATE TABLE IF NOT EXISTS escalations (
  id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, operator_id INTEGER NOT NULL REFERENCES operators(id),
  question TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'logged'
);
CREATE TABLE IF NOT EXISTS daily_metrics (
  day TEXT NOT NULL, machine_id INTEGER NOT NULL REFERENCES machines(id),
  completion_rate REAL NOT NULL, time_score REAL NOT NULL, idle_score REAL NOT NULL,
  safety_score REAL NOT NULL, efficiency REAL NOT NULL, completed_tasks INTEGER NOT NULL,
  total_tasks INTEGER NOT NULL, actual_minutes REAL NOT NULL, predicted_minutes REAL NOT NULL,
  idle_minutes REAL NOT NULL, incident_count INTEGER NOT NULL,
  PRIMARY KEY(day, machine_id)
);
CREATE TABLE IF NOT EXISTS model_metrics (
  model_name TEXT PRIMARY KEY, metrics_json TEXT NOT NULL, trained_at TEXT NOT NULL, noise_level REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_operator_day ON tasks(operator_id, day);
CREATE INDEX IF NOT EXISTS idx_telemetry_machine_time ON telemetry(machine_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_incidents_machine_time ON incidents(machine_id, created_at);
"""


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)

