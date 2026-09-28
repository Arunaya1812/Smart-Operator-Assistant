# Entity-Relationship Diagram

The operational store is SQLite with foreign-key enforcement enabled. `WEATHER_DAILY`, `MODEL_METRICS`, and the date portion of `DAILY_METRICS` are intentionally independent records; matching dates are joined by application logic rather than declared foreign keys.

```mermaid
erDiagram
    OPERATORS ||--o{ TASKS : receives
    MACHINES ||--o{ TASKS : performs
    TASKS o|--o{ TASKS : prerequisite_for

    MACHINES ||--o{ TELEMETRY : produces
    OPERATORS o|--o{ TELEMETRY : associated_with
    TASKS o|--o{ TELEMETRY : sampled_during

    MACHINES ||--o{ INCIDENTS : experiences
    OPERATORS o|--o{ INCIDENTS : involved_in
    TASKS o|--o{ INCIDENTS : occurs_during

    MACHINES ||--o{ TICKETS : has
    OPERATORS ||--o{ TICKETS : raises
    INCIDENTS o|--o{ TICKETS : may_create

    OPERATORS ||--o{ OPERATOR_LESSONS : completes
    LESSONS ||--o{ OPERATOR_LESSONS : recorded_as
    OPERATORS ||--o{ ESCALATIONS : requests
    MACHINES ||--o{ DAILY_METRICS : summarized_by

    OPERATORS {
        int id PK
        string name
        string expertise
        int points
    }

    MACHINES {
        int id PK
        string machine_code UK
        string machine_type
        float age_years
        float service_hours
        float last_service_hours
    }

    WEATHER_DAILY {
        string day PK
        string condition
        float temperature_c
        float wind_kph
        float precipitation_mm
    }

    TASKS {
        int id PK
        string day
        int operator_id FK
        int machine_id FK
        string title
        string task_type
        int priority
        int prerequisite_id FK
        string status
        int planned_start_hour
        float predicted_minutes
        float actual_minutes
        int points
        string started_at
        string completed_at
    }

    TELEMETRY {
        int id PK
        string recorded_at
        int machine_id FK
        int operator_id FK
        int task_id FK
        float speed_kph
        float vibration
        float temperature_c
        float load_pct
        float idle_minutes
        float harsh_swing
        float proximity_m
        boolean seatbelt
        float drowsiness
        float component_health
        string anomaly_label
    }

    INCIDENTS {
        int id PK
        string created_at
        int machine_id FK
        int operator_id FK
        int task_id FK
        string event_type
        string severity
        string message
        boolean authority_alerted
        string auto_action
    }

    TICKETS {
        int id PK
        string created_at
        int machine_id FK
        int operator_id FK
        int incident_id FK
        string component
        string description
        string status
    }

    LESSONS {
        int id PK
        string lesson_type UK
        string title
        string narration
        string video_url
    }

    OPERATOR_LESSONS {
        int operator_id PK, FK
        int lesson_id PK, FK
        string completed_at
    }

    ESCALATIONS {
        int id PK
        string created_at
        int operator_id FK
        string question
        string status
    }

    DAILY_METRICS {
        string day PK
        int machine_id PK, FK
        float completion_rate
        float time_score
        float idle_score
        float safety_score
        float efficiency
        int completed_tasks
        int total_tasks
        float actual_minutes
        float predicted_minutes
        float idle_minutes
        int incident_count
    }

    MODEL_METRICS {
        string model_name PK
        string metrics_json
        string trained_at
        float noise_level
    }
```

## Relationship notes

- A task belongs to one operator and one machine and may reference one prerequisite task.
- Telemetry always belongs to a machine; operator and task links are nullable for samples outside a task context.
- Incidents always belong to a machine and may be linked to an operator and task.
- A ticket always belongs to a machine and operator and may originate from an incident.
- `OPERATOR_LESSONS` resolves the many-to-many relationship between operators and lessons and records completion time.
- Daily metrics use the composite key `(day, machine_id)` and measure the machine, not the operator.
- Chroma documents and Joblib model files are artifact stores, not relational entities, so they are shown in the system architecture rather than this ER model.

