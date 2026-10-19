import os, sqlite3
from contextlib import contextmanager
DATABASE_URL=os.getenv("HEALTH_DB",os.path.join(os.path.dirname(os.path.dirname(__file__)),"health.db"))
SCHEMA="""CREATE TABLE IF NOT EXISTS patients (id TEXT PRIMARY KEY,name TEXT NOT NULL,hospital_id TEXT NOT NULL,date_of_birth TEXT,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT,patient_id TEXT NOT NULL REFERENCES patients(id),filename TEXT NOT NULL,content_type TEXT,uploaded_by TEXT NOT NULL,uploaded_at TEXT NOT NULL,notes TEXT);CREATE TABLE IF NOT EXISTS measurements (id INTEGER PRIMARY KEY AUTOINCREMENT,patient_id TEXT NOT NULL REFERENCES patients(id),metric TEXT NOT NULL,value REAL NOT NULL,unit TEXT NOT NULL,measured_at TEXT NOT NULL,recorded_by TEXT NOT NULL,source_report_id INTEGER REFERENCES reports(id));CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id TEXT NOT NULL,actor_role TEXT NOT NULL,action TEXT NOT NULL,patient_id TEXT,details TEXT,created_at TEXT NOT NULL);CREATE INDEX IF NOT EXISTS idx_measurements_patient_metric ON measurements(patient_id,metric,measured_at);CREATE TABLE IF NOT EXISTS attribution_recipients (recipient_id TEXT PRIMARY KEY,kem_public_key TEXT NOT NULL,kem_private_key TEXT NOT NULL,signature_public_key TEXT NOT NULL,signature_private_key TEXT NOT NULL,created_at TEXT NOT NULL,algorithms TEXT NOT NULL);CREATE TABLE IF NOT EXISTS attribution_packages (package_id TEXT PRIMARY KEY,recipient_id TEXT NOT NULL,nonce TEXT NOT NULL,ciphertext TEXT NOT NULL,encapsulated_key TEXT NOT NULL,wrapped_nonce TEXT NOT NULL,wrapped_key TEXT NOT NULL,metadata TEXT NOT NULL,created_at TEXT NOT NULL,algorithms TEXT NOT NULL);CREATE TABLE IF NOT EXISTS attribution_ledger (sequence INTEGER PRIMARY KEY,previous_hash TEXT NOT NULL,block TEXT NOT NULL,block_hash TEXT NOT NULL);"""
@contextmanager
def connection():
 conn=sqlite3.connect(os.getenv("HEALTH_DB",DATABASE_URL)); conn.row_factory=sqlite3.Row; conn.execute("PRAGMA foreign_keys=ON")
 try: yield conn; conn.commit()
 finally: conn.close()
def init_db():
 with connection() as c:c.executescript(SCHEMA)
