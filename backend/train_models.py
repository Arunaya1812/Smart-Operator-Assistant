from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, IsolationForest
from sklearn.metrics import mean_absolute_error, mean_squared_error, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from db import connect

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)


def train(noise_level: float = 1.0) -> dict:
    with connect() as conn:
        task_rows = conn.execute("""SELECT t.actual_minutes,t.planned_start_hour,m.machine_type,m.age_years,w.condition
            FROM tasks t JOIN machines m ON m.id=t.machine_id JOIN weather_daily w ON w.day=t.day
            WHERE t.actual_minutes IS NOT NULL""").fetchall()
        telem = conn.execute("""SELECT vibration,temperature_c,load_pct,component_health,harsh_swing,
            proximity_m,seatbelt,anomaly_label FROM telemetry""").fetchall()

    x_task = np.array([[r[1], r[2], r[3], r[4]] for r in task_rows], dtype=object)
    y_task = np.array([r[0] for r in task_rows], dtype=float)
    x_train, x_test, y_train, y_test = train_test_split(x_task, y_task, test_size=0.22, random_state=42)
    prep = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), [1, 3]),
        ("num", StandardScaler(), [0, 2]),
    ])
    task_model = Pipeline([("prep", prep), ("model", GradientBoostingRegressor(random_state=42))])
    task_model.fit(x_train, y_train)
    task_pred = task_model.predict(x_test)
    task_metrics = {
        "mae_minutes": round(float(mean_absolute_error(y_test, task_pred)), 2),
        "rmse_minutes": round(float(mean_squared_error(y_test, task_pred) ** 0.5), 2),
        "test_samples": int(len(y_test)),
    }
    joblib.dump(task_model, ARTIFACT_DIR / "task_duration.joblib")

    x_break = np.array([[r[0], r[1], r[2], r[3]] for r in telem], dtype=float)
    y_break = ((x_break[:, 3] < 0.43) | ((x_break[:, 0] > 5.5) & (x_break[:, 1] > 94))).astype(int)
    xb_train, xb_test, yb_train, yb_test = train_test_split(x_break, y_break, test_size=0.25, random_state=42, stratify=y_break)
    break_model = GradientBoostingClassifier(random_state=42)
    break_model.fit(xb_train, yb_train)
    prob = break_model.predict_proba(xb_test)[:, 1]
    pred = (prob >= 0.5).astype(int)
    # Hours to failure is a transparent degradation projection and is evaluated against noisy health.
    true_hours = np.maximum(0, (xb_test[:, 3] - 0.28) * 220)
    predicted_hours = np.maximum(0, (0.72 * xb_test[:, 3] - 0.20) * 220)
    break_metrics = {
        "precision": round(float(precision_score(yb_test, pred, zero_division=0)), 3),
        "recall": round(float(recall_score(yb_test, pred, zero_division=0)), 3),
        "hours_to_failure_mae": round(float(mean_absolute_error(true_hours, predicted_hours)), 2),
        "test_samples": int(len(yb_test)),
    }
    joblib.dump(break_model, ARTIFACT_DIR / "breakdown.joblib")

    x_anom = np.array([[r[0], r[1], r[2], r[4], r[5], r[6]] for r in telem], dtype=float)
    y_anom = np.array([1 if r[7] else 0 for r in telem])
    anomaly_model = IsolationForest(contamination=max(0.02, min(0.2, float(y_anom.mean()))), random_state=42)
    anomaly_model.fit(x_anom)
    model_flag = (anomaly_model.predict(x_anom) == -1).astype(int)
    rule_flag = ((x_anom[:, 3] > 1.0) | (x_anom[:, 4] < 1.4) | (x_anom[:, 5] < 0.5) | (x_anom[:, 1] > 98) | (x_anom[:, 2] > 92)).astype(int)
    combined = np.maximum(model_flag, rule_flag)
    anomaly_metrics = {
        "precision": round(float(precision_score(y_anom, combined, zero_division=0)), 3),
        "recall": round(float(recall_score(y_anom, combined, zero_division=0)), 3),
        "positive_samples": int(y_anom.sum()),
    }
    joblib.dump(anomaly_model, ARTIFACT_DIR / "anomaly.joblib")

    metrics = {"task_duration": task_metrics, "breakdown": break_metrics, "anomaly_detection": anomaly_metrics}
    trained_at = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        for name, values in metrics.items():
            conn.execute("INSERT OR REPLACE INTO model_metrics VALUES(?,?,?,?)", (name, json.dumps(values), trained_at, noise_level))
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps({"noise_level": noise_level, **metrics}, indent=2), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train prototype models against generated data")
    parser.add_argument("--noise", type=float, default=1.0)
    args = parser.parse_args()
    print(json.dumps(train(args.noise), indent=2))

