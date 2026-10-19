# Patient health monitoring backend

Install with `pip install -r requirements.txt`; run `SEED_DEMO=1 uvicorn app.main:app --app-dir backend --reload` from the repository root. SQLite defaults to `backend/health.db`; override with `HEALTH_DB`. Synthetic records are inserted only when `SEED_DEMO=1` or `python -m app.seed` is run.

Demo identity uses `X-Demo-User`, `X-Demo-Role` (`patient`/`doctor`), and `X-Demo-Hospital`; defaults are patient-001/patient/hospital-a. Patients can read only themselves, and doctors only their hospital. Corrections require a doctor and create an audit event. Endpoints include `/health`, dashboard/measurements, report upload/list, and measurement correction.
