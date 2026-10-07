"""
Unit and integration tests for Universal Slip Reader and Guardrails.
All LLM calls are mocked, zero external network dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.auth import verify_advisor_jwt
    from app.engine.grading import GradingScale, GradeDefinition
    from app.engine.slip_validation import validate_slip
    from app.engine.universal_reader import extract_with_llm
    import app.v1.endpoints.audit as audit
except ImportError:
    from backend.app.main import app
    from backend.app.core.auth import verify_advisor_jwt
    from backend.app.engine.grading import GradingScale, GradeDefinition
    from backend.app.engine.slip_validation import validate_slip
    from backend.app.engine.universal_reader import extract_with_llm
    import backend.app.v1.endpoints.audit as audit


@pytest.fixture
def sample_scale():
    return GradingScale("TEST_TENANT", [
        GradeDefinition("A+", 4.00, 1, True, True, True),
        GradeDefinition("A",  4.00, 2, True, True, True),
        GradeDefinition("A-", 3.67, 3, True, True, True),
        GradeDefinition("B+", 3.33, 4, True, True, True),
        GradeDefinition("B",  3.00, 5, True, True, True),
        GradeDefinition("C+", 2.33, 6, True, True, True),
        GradeDefinition("C",  2.00, 7, True, True, True),
        GradeDefinition("D+", 1.33, 8, True, True, True),
        GradeDefinition("D",  1.00, 9, False, True, False),
        GradeDefinition("E",  0.00, 10, False, True, False),
        GradeDefinition("HL", None, None, True, False, True),
        GradeDefinition("EX", None, None, True, False, True),
    ])


# ---------------------------------------------------------------------------
# Guardrail Pure Function Tests
# ---------------------------------------------------------------------------
def test_guardrail_unknown_grade(sample_scale):
    slip_data = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [{"code": "CS101", "grade": "Z", "credits": 3}],
            "printed_gpa": None,
        }],
        "matric_no": "A24CS0001",
    }
    warnings, needs_review = validate_slip(slip_data, sample_scale, expected_matric="A24CS0001")
    assert needs_review is True
    assert any("Unknown grade 'Z'" in w for w in warnings)


def test_guardrail_gpa_mismatch(sample_scale):
    # 3 credits of grade A (4.0) -> computed GPA 4.00, but printed is 2.50
    slip_data = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [{"code": "CS101", "grade": "A", "credits": 3}],
            "printed_gpa": 2.50,
        }],
        "matric_no": "A24CS0001",
    }
    warnings, needs_review = validate_slip(slip_data, sample_scale, expected_matric="A24CS0001")
    assert needs_review is True
    assert any("GPA mismatch" in w for w in warnings)


def test_guardrail_matric_mismatch(sample_scale):
    slip_data = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [{"code": "CS101", "grade": "A", "credits": 3}],
            "printed_gpa": 4.00,
        }],
        "matric_no": "A20EC0001",
    }
    warnings, needs_review = validate_slip(slip_data, sample_scale, expected_matric="A24MJ5050")
    assert needs_review is True
    assert any("This slip may belong to someone else" in w for w in warnings)


def test_guardrail_decimal_credits(sample_scale):
    slip_data = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [{"code": "CS101", "grade": "A", "credits": 1.5}],
            "printed_gpa": 4.00,
        }],
        "matric_no": "A24CS0001",
    }
    warnings, needs_review = validate_slip(slip_data, sample_scale, expected_matric="A24CS0001")
    assert needs_review is True
    assert any("Decimal credits (1.5)" in w for w in warnings)


# ---------------------------------------------------------------------------
# Endpoint & Decision Logic Tests
# ---------------------------------------------------------------------------
class _FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = {}

    def select(self, *_a, **_k):
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
            {"id": "OTHER_UNI", "slip_profile": None, "repeat_policy": "latest"},
        ],
        "uploaded_documents": [
            {
                "id": "doc-utm-confident",
                "matric_no": "A24MJ5050",
                "file_path": "slips/utm_confident.pdf",
                "processing_status": "Pending_Student_Verification",
            },
            {
                "id": "doc-utm-incomplete",
                "matric_no": "A24MJ5050",
                "file_path": "slips/utm_incomplete.pdf",
                "processing_status": "Pending_Student_Verification",
            },
            {
                "id": "doc-other",
                "matric_no": "U2024001",
                "file_path": "slips/other.pdf",
                "processing_status": "Pending_Student_Verification",
            },
            {
                "id": "doc-scanned",
                "matric_no": "A24MJ5050",
                "file_path": "slips/scanned.pdf",
                "processing_status": "Pending_Student_Verification",
            },
        ],
        "students": [
            {"matric_no": "A24MJ5050", "user_id": "student-1", "tenant_id": "UTM"},
            {"matric_no": "U2024001", "user_id": "student-2", "tenant_id": "OTHER_UNI"},
        ],
        "academic_records": [],
    }


def test_utm_confident_text_uses_rules_no_llm(mock_db, sample_scale):
    """Confident UTM text with semester, session, and course uses rules without invoking LLM."""
    client = TestClient(app)
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "sub": "student-1",
        "app_metadata": {"tenant_id": "UTM"},
    }

    utm_text_lines = [
        "UNIVERSITI TEKNOLOGI MALAYSIA",
        "MATRIC NO: A24MJ5050",
        "NAME: AHMAD FAHMI",
        "SEMESTER 1 SESSION 2024/2025",
        "SCSE1203 SOFTWARE ENGINEERING PRINCIPLES A 4.00 3 12.00 L",
        "PNG : 4.00 PNGK : 4.00",
    ]

    with patch.object(audit.supabase_svc, "client", _FakeDBClient(mock_db)), \
         patch.object(audit.supabase_svc, "download_transcript_bytes", return_value=b"%PDF-1.4 mock"), \
         patch("fitz.open"), \
         patch.object(audit.PDFExtractor, "extract_text_lines_from_bytes", return_value=utm_text_lines), \
         patch.object(audit, "load_scale", return_value=sample_scale), \
         patch.object(audit, "extract_with_llm") as mock_llm:

        res = client.post("/api/v1/audit/extract", json={"file_path": "slips/utm_confident.pdf"})
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["source"] == "rules"
        assert data["model"] is None
        assert len(data["courses"]) == 1
        assert data["courses"][0]["is_ai_parsed"] is False
        assert data["courses"][0]["course_code"] == "SCSE1203"
        mock_llm.assert_not_called()


def test_utm_text_missing_semester_uses_ai_path(mock_db, sample_scale):
    """UTM text missing semester is NOT confident -> falls back to universal AI reader."""
    client = TestClient(app)
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "sub": "student-1",
        "app_metadata": {"tenant_id": "UTM"},
    }

    # Incomplete lines: has course, but NO semester/session header
    incomplete_lines = [
        "UNIVERSITI TEKNOLOGI MALAYSIA",
        "MATRIC NO: A24MJ5050",
        "SCSE1203 SOFTWARE ENGINEERING PRINCIPLES A 4.00 3 12.00 L",
    ]

    mock_ai_output = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [{
                "code": "SCSE1203",
                "name": "Software Engineering Principles",
                "credits": 3,
                "grade": "A",
            }],
            "printed_gpa": 4.00,
            "printed_cgpa": 4.00,
        }],
        "matric_no": "A24MJ5050",
    }

    with patch.object(audit.supabase_svc, "client", _FakeDBClient(mock_db)), \
         patch.object(audit.supabase_svc, "download_transcript_bytes", return_value=b"%PDF-1.4 mock"), \
         patch("fitz.open"), \
         patch.object(audit.PDFExtractor, "extract_text_lines_from_bytes", return_value=incomplete_lines), \
         patch.object(audit, "load_scale", return_value=sample_scale), \
         patch.object(audit, "extract_with_llm", return_value=mock_ai_output) as mock_llm:

        res = client.post("/api/v1/audit/extract", json={"file_path": "slips/utm_incomplete.pdf"})
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["source"] == "ai"
        assert data["courses"][0]["is_ai_parsed"] is True
        mock_llm.assert_called_once()


def test_synthetic_non_utm_slip_uses_ai_path(mock_db, sample_scale):
    """A synthetic non-UTM university transcript routes directly to universal AI reader."""
    client = TestClient(app)
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "sub": "student-2",
        "app_metadata": {"tenant_id": "OTHER_UNI"},
    }

    non_utm_lines = [
        "METROPOLITAN UNIVERSITY OF TECHNOLOGY",
        "Student Registration: U2024001",
        "Term: Fall 2024",
        "CS101 Intro to CS - Grade: A, Credits: 4",
        "MATH201 Calculus - Grade: B+, Credits: 3",
    ]

    mock_ai_output = {
        "semesters": [{
            "semester_no": 1,
            "session": "2024/2025",
            "courses": [
                {"code": "CS101", "name": "Intro to CS", "credits": 4, "grade": "A"},
                {"code": "MATH201", "name": "Calculus", "credits": 3, "grade": "B+"},
            ],
            "printed_gpa": 3.71,
            "printed_cgpa": 3.71,
        }],
        "matric_no": "U2024001",
    }

    with patch.object(audit.supabase_svc, "client", _FakeDBClient(mock_db)), \
         patch.object(audit.supabase_svc, "download_transcript_bytes", return_value=b"%PDF-1.4 mock"), \
         patch("fitz.open"), \
         patch.object(audit.PDFExtractor, "extract_text_lines_from_bytes", return_value=non_utm_lines), \
         patch.object(audit, "load_scale", return_value=sample_scale), \
         patch.object(audit, "extract_with_llm", return_value=mock_ai_output) as mock_llm:

        res = client.post("/api/v1/audit/extract", json={"file_path": "slips/other.pdf"})
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["source"] == "ai"
        assert len(data["courses"]) == 2
        assert data["courses"][0]["course_code"] == "CS101"
        assert data["courses"][0]["is_ai_parsed"] is True
        mock_llm.assert_called_once()


def test_scanned_pdf_returns_422(mock_db, sample_scale):
    """Scanned PDF with no extractable text layer must return 422 with exact user-facing message."""
    client = TestClient(app)
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "sub": "student-1",
        "app_metadata": {"tenant_id": "UTM"},
    }

    with patch.object(audit.supabase_svc, "client", _FakeDBClient(mock_db)), \
         patch.object(audit.supabase_svc, "download_transcript_bytes", return_value=b"%PDF-1.4 mock"), \
         patch("fitz.open"), \
         patch.object(audit.PDFExtractor, "extract_text_lines_from_bytes", return_value=[]):

        res = client.post("/api/v1/audit/extract", json={"file_path": "slips/scanned.pdf"})
        assert res.status_code == 422
        assert res.json()["detail"] == "Scanned slips aren't supported yet — please upload the original PDF from your student portal."


def test_multi_semester_saved_correctly(sample_scale):
    """Validates that multi-semester approval saves each course under its respective semester."""
    mock_db = {
        "uploaded_documents": [{
            "id": "doc-multi",
            "matric_no": "A24MJ5050",
            "processing_status": "Pending_Advisor_Approval",
        }],
        "tenants": [{"id": "UTM", "repeat_policy": "latest"}],
        "degree_templates": [{"id": "tpl-1", "tenant_id": "UTM"}],
        "template_courses": [],
        "students": [{"matric_no": "A24MJ5050", "advisor_staff_id": "STAFF-001", "tenant_id": "UTM"}],
        "advisors": [{"staff_id": "STAFF-001", "tenant_id": "UTM", "user_id": "adv-uid"}],
    }

    client = TestClient(app)
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "sub": "adv-uid",
        "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"},
    }

    mock_catalog = {
        "SECJ1013": {"course_code": "SECJ1013", "prerequisites": {"type": "AND", "courses": []}},
        "SECJ1023": {"course_code": "SECJ1023", "prerequisites": {"type": "AND", "courses": []}},
    }

    req = {
        "document_id": "doc-multi",
        "matric_number": "A24MJ5050",
        "academic_session": "2024/2025",
        "semester": 2,
        "courses": [
            {
                "course_code": "SECJ1013",
                "course_name": "Programming Technique I",
                "grade": "A",
                "credit_hour": 3,
                "credits": 3,
                "session_semester": "SEM 1 2023/2024",
            },
            {
                "course_code": "SECJ1023",
                "course_name": "Programming Technique II",
                "grade": "B+",
                "credit_hour": 3,
                "credits": 3,
                "session_semester": "SEM 2 2023/2024",
            },
        ],
    }

    with patch.object(audit.supabase_svc, "client", _FakeDBClient(mock_db)), \
         patch.object(audit, "load_scale", return_value=sample_scale), \
         patch.object(audit.supabase_svc, "get_university_course_catalog", return_value=mock_catalog), \
         patch.object(audit.supabase_svc, "get_or_create_student", return_value={"id": "s1", "matric_number": "A24MJ5050", "student_name": "Student"}), \
         patch.object(audit.supabase_svc, "get_student_block_exempted_credits", return_value=(0, None)), \
         patch.object(audit.supabase_svc, "persist_audit_results", return_value="audit-123") as mock_persist:

        res = client.post("/api/v1/audit/finalize-approval", json=req)
        assert res.status_code == 200
        mock_persist.assert_called_once()
        saved_records = mock_persist.call_args[1]["records"]
        course1 = next(r for r in saved_records if r.course_code == "SECJ1013")
        course2 = next(r for r in saved_records if r.course_code == "SECJ1023")
        assert course1.semester == "SEM 1 2023/2024"
        assert course2.semester == "SEM 2 2023/2024"

