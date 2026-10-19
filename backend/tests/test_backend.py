import os
import pytest
from app.trends import calculate_trend

def test_trend_hba1c_uses_percentage_points():
    result=calculate_trend([("2025-01",7.8,"%"),("2025-02",6.9,"%")],"HbA1c")
    assert result["change"] == -0.9
    assert result["percentage_point_change"] == -0.9

def test_trend_zero_denominator_and_insufficient_data():
    assert calculate_trend([("a",0,"mg/dL"),("b",2,"mg/dL")])["percentage_change"] is None
    assert calculate_trend([("a",2,"mg/dL")])["status"] == "insufficient_data"

def test_trend_rejects_incomparable_units():
    assert calculate_trend([("a",2,"mg/dL"),("b",2,"mmol/L")])["status"] == "incomparable_units"

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None

def setup_module():
    if TestClient is None: return
    os.environ["HEALTH_DB"] = os.path.join(os.path.dirname(__file__), "test.db")
    try: os.remove(os.environ["HEALTH_DB"])
    except FileNotFoundError: pass
    from app.db import init_db, connection
    init_db()
    with connection() as c:
        c.execute("INSERT INTO patients VALUES (?,?,?,?,?)",("p1","A","h1","2000","now"))
        c.execute("INSERT INTO patients VALUES (?,?,?,?,?)",("p2","B","h2","2000","now"))
        c.execute("INSERT INTO measurements(patient_id,metric,value,unit,measured_at,recorded_by) VALUES(?,?,?,?,?,?)",("p1","HbA1c",7,"%","2025","seed"))

def test_patient_and_hospital_isolation():
    if TestClient is None: pytest.skip("FastAPI dependencies unavailable")
    from app.main import app
    with TestClient(app) as client:
        assert client.get("/patients/p2/dashboard",headers={"X-Demo-User":"p1","X-Demo-Role":"patient"}).status_code == 403
        assert client.get("/patients/p2/dashboard",headers={"X-Demo-User":"d","X-Demo-Role":"doctor","X-Demo-Hospital":"h1"}).status_code == 403

def test_doctor_correction_creates_audit():
    if TestClient is None: pytest.skip("FastAPI dependencies unavailable")
    from app.main import app
    with TestClient(app) as client:
        response=client.post("/patients/p1/measurements/correction",headers={"X-Demo-User":"d","X-Demo-Role":"doctor","X-Demo-Hospital":"h1"},json={"measurement_id":1,"value":6.5,"unit":"%","reason":"verified lab result"})
        assert response.status_code == 200 and response.json()["audit_recorded"]
        from app.db import connection
        with connection() as c: assert c.execute("SELECT COUNT(*) FROM audit_events WHERE action='measurement.corrected'").fetchone()[0] == 1
