import sqlite3
import os

DB_PATH = "dwrs_local.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS districts (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    state               TEXT NOT NULL,
    boundary_polygon    TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id                  TEXT PRIMARY KEY,
    username            TEXT UNIQUE NOT NULL,
    email               TEXT UNIQUE,
    password_hash       TEXT NOT NULL,
    totp_secret         TEXT,
    role                TEXT NOT NULL,
    district_id         TEXT REFERENCES districts(id),
    is_suspended        INTEGER DEFAULT 0,
    suspension_reason   TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS officers (
    id                  TEXT PRIMARY KEY REFERENCES users(id),
    badge_number        TEXT UNIQUE NOT NULL,
    district_id         TEXT NOT NULL REFERENCES districts(id),
    trust_score         REAL DEFAULT 1.000,
    registrations_count INTEGER DEFAULT 0,
    verifications_count INTEGER DEFAULT 0,
    anomaly_flags       INTEGER DEFAULT 0,
    confirmed_violations INTEGER DEFAULT 0,
    base_geo_lat        REAL,
    base_geo_lng        REAL,
    is_suspended        INTEGER DEFAULT 0,
    suspended_at        TEXT,
    suspended_reason    TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workers (
    id                  TEXT PRIMARY KEY,
    aadhaar_hash        TEXT UNIQUE NOT NULL,
    aadhaar_enc         BLOB NOT NULL,
    full_name_enc       BLOB NOT NULL,
    dob                 TEXT NOT NULL,
    gender              TEXT,
    photo_url           TEXT,
    face_embedding      BLOB,
    mobile_hash         TEXT,
    mobile_enc          BLOB,
    address             TEXT NOT NULL,
    district_id         TEXT REFERENCES districts(id),
    risk_score          INTEGER DEFAULT 0,
    risk_level          TEXT,
    status              TEXT DEFAULT 'pending',
    registration_no     TEXT UNIQUE,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS registrations (
    id                  TEXT PRIMARY KEY,
    worker_id           TEXT NOT NULL REFERENCES workers(id),
    registration_mode   TEXT NOT NULL,
    officer_id          TEXT REFERENCES users(id),
    employer_id         TEXT REFERENCES users(id),
    geo_lat             REAL,
    geo_lng             REAL,
    geo_accuracy_meters REAL,
    device_fingerprint  TEXT,
    offline_batch_id    TEXT,
    offline_captured_at TEXT,
    consent_recorded    INTEGER NOT NULL DEFAULT 0,
    consent_witness     TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS verification_records (
    id                  TEXT PRIMARY KEY,
    worker_id           TEXT NOT NULL REFERENCES workers(id),
    officer_id          TEXT NOT NULL REFERENCES users(id),
    face_match_score    REAL,
    geo_match_passed    INTEGER,
    geo_distance_km     REAL,
    id_validation_passed INTEGER,
    liveness_passed     INTEGER,
    decision            TEXT NOT NULL,
    notes               TEXT,
    verified_at         TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_scores (
    id                  TEXT PRIMARY KEY,
    entity_id           TEXT NOT NULL,
    entity_type         TEXT NOT NULL,
    total_score         INTEGER NOT NULL,
    risk_level          TEXT NOT NULL,
    rule_score          INTEGER,
    ml_anomaly_score    REAL,
    rule_flags          TEXT,
    explanation         TEXT,
    computed_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    computed_by         TEXT DEFAULT 'system',
    version             INTEGER
);

CREATE TABLE IF NOT EXISTS officer_activity_logs (
    id                  TEXT PRIMARY KEY,
    officer_id          TEXT NOT NULL REFERENCES users(id),
    action_type         TEXT NOT NULL,
    entity_id           TEXT,
    geo_lat             REAL,
    geo_lng             REAL,
    session_id          TEXT,
    ip_address          TEXT,
    extra_data          TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_records (
    id                  TEXT PRIMARY KEY,
    actor_id            TEXT NOT NULL,
    actor_role          TEXT NOT NULL,
    action              TEXT NOT NULL,
    entity_type         TEXT NOT NULL,
    entity_id           TEXT,
    before_state        TEXT,
    after_state         TEXT,
    ip_address          TEXT,
    session_id          TEXT,
    prev_hash           TEXT NOT NULL,
    record_hash         TEXT NOT NULL UNIQUE,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS offline_batches (
    id                  TEXT PRIMARY KEY,
    officer_id          TEXT NOT NULL REFERENCES users(id),
    device_fingerprint  TEXT,
    records_count       INTEGER DEFAULT 0,
    synced_count        INTEGER DEFAULT 0,
    expired_count       INTEGER DEFAULT 0,
    captured_location   TEXT,
    sync_started_at     TEXT,
    sync_completed_at   TEXT,
    status              TEXT DEFAULT 'pending',
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_queue (
    id                  TEXT PRIMARY KEY,
    worker_id           TEXT NOT NULL REFERENCES workers(id),
    risk_score          INTEGER NOT NULL,
    risk_flags          TEXT,
    assigned_to         TEXT REFERENCES users(id),
    status              TEXT DEFAULT 'pending',
    decision_reason     TEXT,
    decided_at          TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE VIEW IF NOT EXISTS officer_trust_metrics AS
SELECT
    o.id,
    o.badge_number,
    o.trust_score,
    0 AS weekly_registrations,
    0 AS daily_registrations,
    0 AS failed_verifications_on_registrants,
    0 AS avg_face_score_on_registrants,
    o.anomaly_flags,
    o.confirmed_violations,
    o.is_suspended
FROM officers o;
"""

def init_db():
    if os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} already exists. Skipping initialization.")
        return

    print("Initializing SQLite database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Execute statements one by one
    for statement in SCHEMA.split(';'):
        if statement.strip():
            cursor.execute(statement)

    conn.commit()
    conn.close()
    print("Database initialized successfully!")

if __name__ == "__main__":
    init_db()
