"""
Unit & integration tests for Scanned Slip Vision Reader (Task A).
Mocked vision model, zero external network calls.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.config import settings
    from app.core.auth import verify_advisor_jwt
    from app.engine.grading import GradingScale, GradeDefinition
    import app.engine.scanned_reader as scanned_reader
    import app.v1.endpoints.audit as audit
except ImportError:
    from backend.app.main import app
    from backend.app.core.config import settings
    from backend.app.core.auth import verify_advisor_jwt
    from backend.app.engine.grading import GradingScale, GradeDefinition
    import backend.app.engine.scanned_reader as scanned_reader
    import backend.app.v1.endpoints.audit as audit


@pytest.fixture
def sample_scale():
    return GradingScale("UTM", [
        GradeDefinition("A+", 4.00, 1, True, True, True),
        GradeDefinition("A",  4.00, 2, True, True, True),
        GradeDefinition("A-", 3.67, 3, True, True, True),
        GradeDefinition("B+", 3.33, 4, True, True, True),
        GradeDefinition("B",  3.00, 5, True, True, True),
        GradeDefinition("C",  2.00, 7, True, True, True),
        GradeDefinition("E",  0.00, 10, False, True, False),
    ])


class _FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def limit(self, *_a):
        return self

    def update(self, payload):
        rows = [r for r in self.db.get(self.table, []) if all(r.get(k) == v for k, v in self.filters.items())]
        for r in rows:
            r.update(payload)
        return self

    def execute(self):
        rows = [r for r in self.db.get(self.table, []) if all(r.get(k) == v for k, v in self.filters.items())]
        return type("Res", (), {"data": rows})()


class _FakeDBClient:
    def __init__(self, db):
        self.db = db

    def table(self, name):
        return _FakeQuery(self.db, name)


@pytest.fixture
def mock_db():
    return {
        "tenants": [
            {"id": "UTM", "slip_profile": "utm", "repeat_policy": "latest"},
        ],
        "uploaded_documents": [
            {
                "id": "doc-scanned",
                "matric_no": "A24MJ5050",
                "file_path": "slips/scanned.pdf",
                "processing_status": "Pending_Student_Verification",
            },
        ],
        "students": [
            {"matric_no": "A24MJ5050", "user_id": "student-1", "tenant_id": "UTM"},
        ],
        "advisors": [],
    }


def test_scanned_pdf_routes_to_ai_scan(mock_db, sample_scale, monkeypatch):
    """Scanned PDF with vision model configured routes to ai_scan."""
    monkeypatch.setattr(settings, "LLM_VISION_MODEL", "llama-3.2-11b-vision-preview")
    monkeypatch.setattr(settings, "LLM_API_KEY", "mock-key")

    client = TestClient(app)
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "sub": "student-1",
        "app_metadata": {"tenant_id": "UTM"},
    }

    mock_vision_data = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [
                {"code": "SECJ1013", "name": "Programming Technique I", "credits": 3, "grade": "A"},
            ],
            "printed_gpa": 4.00,
            "printed_cgpa": 4.00,
        }],
        "matric_no": "A24MJ5050",
        "warnings": [],
    }

    with patch.object(audit.supabase_svc, "client", _FakeDBClient(mock_db)), \
         patch.object(audit.supabase_svc, "download_transcript_bytes", return_value=b"%PDF-mock"), \
         patch.object(audit.PDFExtractor, "extract_text_lines_from_bytes", return_value=[]), \
         patch.object(audit, "load_scale", return_value=sample_scale), \
         patch.object(audit, "extract_scanned_transcript", return_value=mock_vision_data) as mock_scan:

        res = client.post("/api/v1/audit/extract", json={"file_path": "slips/scanned.pdf"})
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["source"] == "ai_scan"
        assert data["model"] == "llama-3.2-11b-vision-preview"
        assert len(data["courses"]) == 1
        assert data["courses"][0]["course_code"] == "SECJ1013"
        assert data["courses"][0]["is_ai_parsed"] is True
        mock_scan.assert_called_once()


def test_scanned_pdf_multi_page_merge(monkeypatch):
    """Validates multi-page transcript merge across pages."""
    monkeypatch.setattr(settings, "LLM_VISION_MODEL", "llama-3.2-11b-vision-preview")
    monkeypatch.setattr(settings, "LLM_API_KEY", "mock-key")

    page1_data = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [{"code": "CS101", "name": "Intro CS", "credits": 3, "grade": "A"}],
            "printed_gpa": 4.00,
            "printed_cgpa": None,
        }],
        "matric_no": "A24MJ5050",
    }
    page2_data = {
        "semesters": [
            {
                "semester_no": 1,
                "session": "2024/2025",
                "courses": [{"code": "CS102", "name": "Data Structures", "credits": 3, "grade": "B+"}],
                "printed_gpa": None,
                "printed_cgpa": 3.67,
            },
            {
                "semester_no": 2,
                "session": "2024/2025",
                "courses": [{"code": "CS201", "name": "Algorithms", "credits": 3, "grade": "A-"}],
                "printed_gpa": 3.67,
                "printed_cgpa": 3.67,
            },
        ],
        "matric_no": None,
    }

    mock_pages = [b"png-page-1", b"png-page-2"]

    with patch.object(scanned_reader, "render_pdf_to_images", return_value=mock_pages), \
         patch.object(scanned_reader, "extract_page_with_vision", side_effect=[page1_data, page2_data]):

        result = scanned_reader.extract_scanned_transcript(b"mock-pdf-bytes", tenant_ctx={})
        assert result["matric_no"] == "A24MJ5050"
        semesters = result["semesters"]
        assert len(semesters) == 2

        # Semester 1 merged CS101 and CS102
        sem1 = next(s for s in semesters if s["semester_no"] == 1)
        assert len(sem1["courses"]) == 2
        assert sem1["courses"][0]["code"] == "CS101"
        assert sem1["courses"][1]["code"] == "CS102"
        assert sem1["printed_gpa"] == 4.00
        assert sem1["printed_cgpa"] == 3.67

        # Semester 2 has CS201
        sem2 = next(s for s in semesters if s["semester_no"] == 2)
        assert len(sem2["courses"]) == 1
        assert sem2["courses"][0]["code"] == "CS201"


def test_scanned_pdf_empty_page_warning(monkeypatch):
    """Empty page with 0 courses outputs 'Page N could not be read' warning."""
    monkeypatch.setattr(settings, "LLM_VISION_MODEL", "llama-3.2-11b-vision-preview")
    monkeypatch.setattr(settings, "LLM_API_KEY", "mock-key")

    page1_data = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [{"code": "CS101", "name": "Intro CS", "credits": 3, "grade": "A"}],
            "printed_gpa": 4.00,
            "printed_cgpa": 4.00,
        }],
        "matric_no": "A24MJ5050",
    }
    # Page 2 has no courses
    page2_data = {
        "semesters": [],
        "matric_no": None,
    }

    mock_pages = [b"png-page-1", b"png-page-2"]

    with patch.object(scanned_reader, "render_pdf_to_images", return_value=mock_pages), \
         patch.object(scanned_reader, "extract_page_with_vision", side_effect=[page1_data, page2_data]):

        result = scanned_reader.extract_scanned_transcript(b"mock-pdf-bytes", tenant_ctx={})
        warnings = result.get("warnings", [])
        assert "Page 2 could not be read" in warnings


def test_missing_llm_vision_model_returns_422(mock_db, sample_scale, monkeypatch):
    """Missing LLM_VISION_MODEL keeps 422 with exact user-facing message."""
    monkeypatch.setattr(settings, "LLM_VISION_MODEL", None)

    client = TestClient(app)
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "sub": "student-1",
        "app_metadata": {"tenant_id": "UTM"},
    }

    with patch.object(audit.supabase_svc, "client", _FakeDBClient(mock_db)), \
         patch.object(audit.supabase_svc, "download_transcript_bytes", return_value=b"%PDF-mock"), \
         patch.object(audit.PDFExtractor, "extract_text_lines_from_bytes", return_value=[]), \
         patch.object(audit, "load_scale", return_value=sample_scale):

        res = client.post("/api/v1/audit/extract", json={"file_path": "slips/scanned.pdf"})
        assert res.status_code == 422
        assert res.json()["detail"] == "Scanned slips aren't supported yet — please upload the original PDF from your student portal."


def test_scanned_pdf_more_than_six_pages_returns_422(monkeypatch):
    """PDF with more than 6 pages returns 422 'Please upload at most 6 pages'."""
    # Create fake PyMuPDF doc with 7 pages
    fake_doc = [MagicMock() for _ in range(7)]

    with patch("pymupdf.open", return_value=fake_doc):
        with pytest.raises(Exception) as exc_info:
            scanned_reader.render_pdf_to_images(b"%PDF-mock-7-pages")
        assert exc_info.value.status_code == 422
        assert "Please upload at most 6 pages" in exc_info.value.detail


def test_scanned_pdf_ic_removed_from_output(monkeypatch):
    """National ID numbers (NRIC/MyKad) are completely dropped/redacted from matric_no and courses."""
    monkeypatch.setattr(settings, "LLM_VISION_MODEL", "llama-3.2-11b-vision-preview")
    monkeypatch.setattr(settings, "LLM_API_KEY", "mock-key")

    page_data = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [
                {"code": "CS101", "name": "Programming with IC: 020512-01-1234", "credits": 3, "grade": "A"},
                {"code": "020512-01-1234", "name": "Fake Course", "credits": 3, "grade": "A"},
            ],
            "printed_gpa": 4.00,
            "printed_cgpa": 4.00,
        }],
        # Model wrongly outputted an IC in matric_no
        "matric_no": "020512-01-1234",
    }

    with patch.object(scanned_reader, "render_pdf_to_images", return_value=[b"png-1"]), \
         patch.object(scanned_reader, "extract_page_with_vision", return_value=page_data):

        result = scanned_reader.extract_scanned_transcript(b"mock-pdf", tenant_ctx={})
        assert result["matric_no"] is None  # IC must be dropped

        sem = result["semesters"][0]
        # The course with code == IC should be dropped
        assert len(sem["courses"]) == 1
        valid_course = sem["courses"][0]
        assert valid_course["code"] == "CS101"
        assert "020512-01-1234" not in valid_course["name"]
        assert "[REDACTED-ID]" in valid_course["name"]
