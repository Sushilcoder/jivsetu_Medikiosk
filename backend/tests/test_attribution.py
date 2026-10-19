import json
import pytest

from app import attribution
from app import db


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", str(tmp_path / "attribution.db"))
    db.init_db()
    return tmp_path


def test_pq_algorithm_metadata_is_explicit(store):
    result = attribution.register_recipient("alice")
    assert result["algorithms"]["pq_available"] is attribution.PQ_AVAILABLE
    assert result["algorithms"]["signature"]
    assert result["algorithms"]["kem"]


@pytest.mark.skipif(attribution.AESGCM is None, reason="cryptography optional dependency unavailable")
def test_round_trip_and_unique_watermarks(store):
    attribution.register_recipient("alice")
    package = attribution.create_package("alice", "offline document", {"kind": "demo"})
    first = attribution.decrypt_package(package["package_id"], "alice")
    second = attribution.decrypt_package(package["package_id"], "alice")
    assert first["document"] == second["document"] == "offline document"
    assert first["watermark_id"] != second["watermark_id"]
    assert attribution.extract_watermark(first["watermarked_document"]) == first["watermark_id"]


@pytest.mark.skipif(attribution.AESGCM is None, reason="cryptography optional dependency unavailable")
def test_signature_and_ledger_tamper_detection(store):
    attribution.register_recipient("alice")
    package = attribution.create_package("alice", "signed")
    receipt = attribution.decrypt_package(package["package_id"], "alice")["receipt"]
    assert attribution.verify_watermark(receipt["event"]["watermark_id"])["valid"]
    assert attribution.verify_watermark(receipt["event"]["watermark_id"], "bad")["valid"] is False
    assert attribution.verify_ledger()["valid"]
    with db.connection() as c:
        c.execute("UPDATE attribution_ledger SET block=REPLACE(block, 'document.decrypted', 'tampered') WHERE sequence=1")
    assert attribution.verify_ledger()["valid"] is False
