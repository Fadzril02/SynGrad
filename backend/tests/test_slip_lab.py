"""
Tests for Staging Slip Lab endpoint (Task B).
Zero network dependencies. Tests access control, zero-persistence, and routing.
"""

import io
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.config import settings
    from app.v1.endpoints.lab import verify_lab_access
    from app.engine.grading import GradingScale, GradeDefinition
    import app.v1.endpoints.audit as audit
except ImportError:
    from backend.app.main import app
    from backend.app.core.config import settings
    from backend.app.v1.endpoints.lab import verify_lab_access
    from backend.app.engine.grading import GradingScale, GradeDefinition
    import backend.app.v1.endpoints.audit as audit


@pytest.fixture
def sample_scale():
    return GradingScale("UTM", [
        GradeDefinition("A+", 4.00, 1, True, True, True),
        GradeDefinition("A",  4.00, 2, True, True, True),
        GradeDefinition("B+", 3.33, 4, True, True, True),
        GradeDefinition("B",  3.00, 5, True, True, True),
        GradeDefinition("C",  2.00, 7, True, True, True),
    ])


class _FakeDBClient:
    def __init__(self):
        self.insert_called = False
        self.update_called = False

    def table(self, name):
        mock_table = MagicMock()
        def record_insert(*args, **kwargs):
            self.insert_called = True
            return mock_table
        def record_update(*args, **kwargs):
            self.update_called = True
            return mock_table

        mock_table.insert = record_insert
        mock_table.update = record_update
        mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = type(
            "Res", (), {"data": [{"slip_profile": "utm", "repeat_policy": "latest"}]}
        )()
        return mock_table


def test_lab_404_when_not_staging(monkeypatch):
    """When ENVIRONMENT is not staging, /lab/extract must return 404."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    client = TestClient(app)
    # Even if authenticated, must return 404
    files = {"file": ("test.pdf", b"%PDF-1.4 mock", "application/pdf")}
    data = {"tenant_id": "UTM"}

    res = client.post("/api/v1/lab/extract", files=files, data=data, headers={"Authorization": "Bearer mock-token"})
    assert res.status_code == 404

    # Also test /lab/extract directly
    res2 = client.post("/lab/extract", files=files, data=data, headers={"Authorization": "Bearer mock-token"})
    assert res2.status_code == 404


def test_lab_403_for_non_allowed_email(monkeypatch):
    """When in staging, users whose email is not in LAB_ALLOWED_EMAILS must receive 403."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "LAB_ALLOWED_EMAILS", "advisor@utm.my,admin@syngrad.my")

    client = TestClient(app)
    app.dependency_overrides[verify_lab_access] = lambda: {
        "sub": "user-123",
        "email": "unauthorized@example.com",
    }

    files = {"file": ("test.pdf", b"%PDF-1.4 mock", "application/pdf")}
    data = {"tenant_id": "UTM"}

    res = client.post("/api/v1/lab/extract", files=files, data=data, headers={"Authorization": "Bearer mock"})
    assert res.status_code == 403


def test_lab_nothing_written_to_db_or_storage(sample_scale, monkeypatch):
    """Slip Lab runs extraction and returns diagnostic JSON without writing anything to DB or storage."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "LAB_ALLOWED_EMAILS", "staff@utm.my")

    client = TestClient(app)
    app.dependency_overrides[verify_lab_access] = lambda: {
        "sub": "staff-uid",
        "email": "staff@utm.my",
    }

    fake_db = _FakeDBClient()
    mock_lines = [
        "UNIVERSITI TEKNOLOGI MALAYSIA",
        "KEPUTUSAN PEPERIKSAAN AKHIR",
        "SEMESTER 1 SESI 2024/2025",
        "NAMA : AHMAD FADZRIL",
        "NO. K/P : 020512-01-1234",
        "NO. MATRIK : A24MJ5050",
        "SECJ1013 PROGRAMMING TECHNIQUE I 3 A 4.00",
        "JUMLAH JAM KREDIT KIRA (KK) : 3",
        "JUMLAH JAM KREDIT DAPAT (KD) : 3",
        "PNG : 4.00 PNGK : 4.00",
    ]

    with patch.object(audit.supabase_svc, "client", fake_db), \
         patch.object(audit, "_load_tenant_slip_profile", return_value="utm"), \
         patch.object(audit.PDFExtractor, "extract_text_lines_from_bytes", return_value=mock_lines), \
         patch.object(audit, "load_scale", return_value=sample_scale):

        files = {"file": ("slip.pdf", b"%PDF-1.4 test", "application/pdf")}
        data = {"tenant_id": "UTM"}

        res = client.post("/api/v1/lab/extract", files=files, data=data, headers={"Authorization": "Bearer mock"})
        assert res.status_code == 200
        json_data = res.json()

        # Check required fields
        assert "source" in json_data
        assert "model" in json_data
        assert "semesters" in json_data
        assert "courses" in json_data
        assert "warnings" in json_data
        assert "needs_review" in json_data
        assert "timing" in json_data

        # Verify NOTHING was inserted or updated in DB
        assert fake_db.insert_called is False
        assert fake_db.update_called is False


def test_lab_rules_vs_ai_routing(sample_scale, monkeypatch):
    """Validates that Slip Lab properly routes UTM slip to rules and other slip to AI."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "LAB_ALLOWED_EMAILS", "staff@utm.my")
    monkeypatch.setattr(settings, "LLM_API_KEY", "mock-key")

    client = TestClient(app)
    app.dependency_overrides[verify_lab_access] = lambda: {
        "sub": "staff-uid",
        "email": "staff@utm.my",
    }

    utm_lines = [
        "UNIVERSITI TEKNOLOGI MALAYSIA",
        "SEMESTER 1 SESI 2024/2025",
        "NO. MATRIK : A24MJ5050",
        "SECJ1013 PROGRAMMING TECHNIQUE I 3 A 4.00",
        "PNG : 4.00 PNGK : 4.00",
    ]

    other_lines = [
        "SOME OTHER UNIVERSITY",
        "SEMESTER 1 2024/2025",
        "CS101 Intro to CS Grade A",
    ]

    mock_ai_data = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [{"code": "CS101", "name": "Intro to CS", "credits": 3, "grade": "A"}],
            "printed_gpa": 4.00,
            "printed_cgpa": 4.00,
        }],
        "matric_no": "U2024001",
    }

    fake_db = _FakeDBClient()

    # 1. UTM -> rules
    with patch.object(audit.supabase_svc, "client", fake_db), \
         patch.object(audit, "_load_tenant_slip_profile", return_value="utm"), \
         patch.object(audit.PDFExtractor, "extract_text_lines_from_bytes", return_value=utm_lines), \
         patch.object(audit, "load_scale", return_value=sample_scale):

        files = {"file": ("utm.pdf", b"%PDF-mock", "application/pdf")}
        res = client.post("/api/v1/lab/extract", files=files, data={"tenant_id": "UTM"}, headers={"Authorization": "Bearer mock"})
        assert res.status_code == 200
        assert res.json()["source"] == "rules"

    # 2. Non-UTM -> ai
    with patch.object(audit.supabase_svc, "client", fake_db), \
         patch.object(audit, "_load_tenant_slip_profile", return_value=None), \
         patch.object(audit.PDFExtractor, "extract_text_lines_from_bytes", return_value=other_lines), \
         patch.object(audit, "load_scale", return_value=sample_scale), \
         patch.object(audit, "extract_with_llm", return_value=mock_ai_data):

        files = {"file": ("other.pdf", b"%PDF-mock", "application/pdf")}
        res = client.post("/api/v1/lab/extract", files=files, data={"tenant_id": "OTHER"}, headers={"Authorization": "Bearer mock"})
        assert res.status_code == 200
        assert res.json()["source"] == "ai"
