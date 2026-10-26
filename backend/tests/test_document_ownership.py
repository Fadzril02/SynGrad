"""
Document ownership + server-side verification (uploaded_documents lockdown).
Uses the REAL _load_authorized_document against an in-memory fake database.
"""
import sys
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from unittest.mock import patch

try:
    from app.main import app
    from app.core.auth import verify_advisor_jwt
    import app.v1.endpoints.audit as audit
except ImportError:
    from backend.app.main import app
    from backend.app.core.auth import verify_advisor_jwt
    import backend.app.v1.endpoints.audit as audit

pytestmark = pytest.mark.real_doc_auth


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.payload = db, table, {}, None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def limit(self, *_a):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def execute(self):
        rows = [r for r in self.db[self.table] if all(r.get(k) == v for k, v in self.filters.items())]
        if self.payload is not None:
            for r in rows:
                r.update(self.payload)
        return type("Res", (), {"data": rows})()


class _FakeClient:
    def __init__(self, db):
        self.db = db

    def table(self, name):
        return _Query(self.db, name)


def _db():
    return {
        "uploaded_documents": [{
            "id": "doc-1", "matric_no": "A24MJ5050", "file_path": "slips/a.pdf",
            "processing_status": "Pending_Student_Verification", "fraud_flag": False,
            "extracted_data": {"original_courses": [
                {"course_code": "SCSE1203", "grade": "A", "credits": 3},
                {"course_code": "SCSR1033", "grade": "C+", "credits": 3},
            ]},
        }],
        "students": [
            {"matric_no": "A24MJ5050", "user_id": "stu-uid", "advisor_staff_id": "TEST123", "tenant_id": "UTM"},
        ],
        "advisors": [
            {"user_id": "adv-uid", "staff_id": "TEST123", "tenant_id": "UTM"},
            {"user_id": "other-adv", "staff_id": "OTHER1", "tenant_id": "UTM"},
            {"user_id": "um-adv", "staff_id": "TEST123X", "tenant_id": "UM"},
        ],
    }


@pytest.fixture(autouse=True)
def _restore_auth_override():
    saved = app.dependency_overrides.get(verify_advisor_jwt)
    yield
    if saved is not None:
        app.dependency_overrides[verify_advisor_jwt] = saved
    else:
        app.dependency_overrides.pop(verify_advisor_jwt, None)


@pytest.fixture
def fake_db():
    db = _db()
    with patch.object(audit.supabase_svc, "client", _FakeClient(db)):
        yield db


def test_student_owner_allowed(fake_db):
    doc, role = audit._load_authorized_document({"sub": "stu-uid"}, document_id="doc-1")
    assert role == "student" and doc["id"] == "doc-1"


def test_other_student_forbidden(fake_db):
    with pytest.raises(HTTPException) as e:
        audit._load_authorized_document({"sub": "someone-else"}, document_id="doc-1")
    assert e.value.status_code == 403


def test_assigned_advisor_allowed(fake_db):
    _, role = audit._load_authorized_document({"sub": "adv-uid"}, document_id="doc-1", allow_student=False)
    assert role == "advisor"


def test_other_advisor_forbidden(fake_db):
    with pytest.raises(HTTPException) as e:
        audit._load_authorized_document({"sub": "other-adv"}, document_id="doc-1", allow_student=False)
    assert e.value.status_code == 403


def test_matric_mismatch_forbidden(fake_db):
    with pytest.raises(HTTPException) as e:
        audit._load_authorized_document({"sub": "adv-uid"}, document_id="doc-1",
                                        allow_student=False, expected_matric="B99XX0001")
    assert e.value.status_code == 403


def test_missing_document_404(fake_db):
    with pytest.raises(HTTPException) as e:
        audit._load_authorized_document({"sub": "stu-uid"}, document_id="nope")
    assert e.value.status_code == 404


def test_student_cannot_use_advisor_only_path(fake_db):
    with pytest.raises(HTTPException) as e:
        audit._load_authorized_document({"sub": "stu-uid"}, document_id="doc-1", allow_student=False)
    assert e.value.status_code == 403


def _client_as(sub):
    app.dependency_overrides[verify_advisor_jwt] = lambda: {"sub": sub, "app_metadata": {"tenant_id": "UTM"}}
    return TestClient(app)


def test_submit_verification_flags_changes_server_side(fake_db):
    c = _client_as("stu-uid")
    # Student changes one grade and tries to hide it with is_altered=False
    res = c.post("/api/v1/audit/submit-verification", json={"document_id": "doc-1", "courses": [
        {"course_code": "SCSE1203", "grade": "A", "is_altered": False},
        {"course_code": "SCSR1033", "grade": "A", "is_altered": False, "ai_grade": "A"},
    ]})
    assert res.status_code == 200, res.text
    assert res.json()["altered_count"] == 1
    doc = fake_db["uploaded_documents"][0]
    assert doc["processing_status"] == "Pending_Advisor_Approval"
    changed = doc["extracted_data"]["courses"][1]
    assert changed["is_altered"] is True and changed["ai_grade"] == "C+" and changed["grade"] == "A"
    assert doc["extracted_data"]["courses"][0]["is_altered"] is False
    assert doc["extracted_data"]["original_courses"][1]["grade"] == "C+"


def test_submit_verification_wrong_status_409(fake_db):
    fake_db["uploaded_documents"][0]["processing_status"] = "Approved"
    c = _client_as("stu-uid")
    res = c.post("/api/v1/audit/submit-verification", json={"document_id": "doc-1", "courses": [{}, {}]})
    assert res.status_code == 409


def test_submit_verification_row_count_mismatch_422(fake_db):
    c = _client_as("stu-uid")
    res = c.post("/api/v1/audit/submit-verification", json={"document_id": "doc-1", "courses": [{}]})
    assert res.status_code == 422


def test_submit_verification_by_advisor_forbidden(fake_db):
    c = _client_as("adv-uid")
    res = c.post("/api/v1/audit/submit-verification", json={"document_id": "doc-1", "courses": [{}, {}]})
    assert res.status_code == 403


def test_extract_unauthorized_never_downloads(fake_db):
    c = _client_as("someone-else")
    with patch.object(audit.supabase_svc, "download_transcript_bytes") as dl:
        res = c.post("/api/v1/audit/extract", json={"file_path": "slips/a.pdf"})
    assert res.status_code == 403
    dl.assert_not_called()




def test_reject_purges_slip_and_marks_path(fake_db):
    c = _client_as("adv-uid")
    with patch.object(audit.supabase_svc, "delete_file_from_storage", return_value=True) as rm:
        res = c.post("/api/v1/audit/reject-document", json={"document_id": "doc-1"})
    assert res.status_code == 200 and res.json()["processing_status"] == "Rejected"
    rm.assert_called_once_with(bucket_name="academic-slips", file_path="slips/a.pdf")
    doc = fake_db["uploaded_documents"][0]
    assert doc["processing_status"] == "Rejected" and doc["file_path"] == "[PURGED]"


def test_reject_still_succeeds_when_storage_delete_fails(fake_db, capsys):
    c = _client_as("adv-uid")
    with patch.object(audit.supabase_svc, "delete_file_from_storage", return_value=False):
        res = c.post("/api/v1/audit/reject-document", json={"document_id": "doc-1"})
    assert res.status_code == 200
    doc = fake_db["uploaded_documents"][0]
    assert doc["processing_status"] == "Rejected"
    assert doc["file_path"] == "slips/a.pdf"  # kept so the file can still be found and removed
    assert "[Auto-Purge ERROR]" in capsys.readouterr().out


def test_reject_still_succeeds_when_storage_delete_raises(fake_db, capsys):
    c = _client_as("adv-uid")
    with patch.object(audit.supabase_svc, "delete_file_from_storage", side_effect=RuntimeError("boom")):
        res = c.post("/api/v1/audit/reject-document", json={"document_id": "doc-1"})
    assert res.status_code == 200
    assert fake_db["uploaded_documents"][0]["processing_status"] == "Rejected"
    assert "[Auto-Purge ERROR]" in capsys.readouterr().out


def test_reject_by_other_advisor_never_deletes(fake_db):
    c = _client_as("other-adv")
    with patch.object(audit.supabase_svc, "delete_file_from_storage") as rm:
        res = c.post("/api/v1/audit/reject-document", json={"document_id": "doc-1"})
    assert res.status_code == 403
    rm.assert_not_called()
    assert fake_db["uploaded_documents"][0]["file_path"] == "slips/a.pdf"
