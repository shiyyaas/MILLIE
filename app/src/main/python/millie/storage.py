import os
import sqlite3
import time
from pathlib import Path

def get_db_dir() -> Path:
    millie_home = os.environ.get("MILLIE_HOME")
    if millie_home:
        d = Path(millie_home)
    else:
        d = Path.home() / ".millie"
    d.mkdir(parents=True, exist_ok=True)
    return d

DB_DIR = get_db_dir()
DB_PATH = DB_DIR / "millie.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    protocol TEXT NOT NULL,
    label TEXT NOT NULL,
    category TEXT NOT NULL,
    identifier TEXT,
    rssi REAL,
    threat_score REAL,
    severity TEXT,
    reasons TEXT,
    reviewed INTEGER DEFAULT 0,
    false_positive INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_detections_ts ON detections(ts);
CREATE INDEX IF NOT EXISTS idx_detections_identifier ON detections(identifier);
"""

def get_connection():
    db_dir = get_db_dir()
    db_path = db_dir / "millie.db"
    key = os.environ.get("MILLIE_DB_KEY")
    if key:
        try:
            from sqlcipher3 import dbapi2 as sqlcipher
            conn = sqlcipher.connect(str(db_path))
            conn.execute(f"PRAGMA key = '{key}'")
            conn.executescript(SCHEMA)
            return conn, True
        except ImportError:
            pass
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    return conn, False

def record_detection(conn, protocol, label, category, identifier=None, rssi=None, threat_score=None, severity=None, reasons=None):
    conn.execute(
        "INSERT INTO detections (ts, protocol, label, category, identifier, rssi, threat_score, severity, reasons) VALUES (?,?,?,?,?,?,?,?,?)",
        (time.time(), protocol, label, category, identifier, rssi, threat_score, severity, ",".join(reasons) if reasons else None)
    )
    conn.commit()
