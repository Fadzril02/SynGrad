"""
Unit Tests for UTM Semester Slip Parser, ST Status Codes, Summary Box Extraction, and Approval Verification
"""

import sys
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.auth import verify_advisor_jwt
    from app.engine.parsers.malaysian_regex import MalaysianTranscriptParser
    from app.engine.grading import (
        GradingScale,
        GradeDefinition,
        load_scale
    )
except ImportError:
    from backend.app.main import app
    from backend.app.core.auth import verify_advisor_jwt
    from backend.app.engine.parsers.malaysian_regex import MalaysianTranscriptParser
    from backend.app.engine.grading import (
        GradingScale,
        GradeDefinition,
        load_scale
    )

client = TestClient(app)

AUTH_HEADERS = {"Authorization": "Bearer mock-test-token"}

UTM_GRADE_DEFINITIONS = [
    GradeDefinition(grade="A+", points=4.00, rank=1, is_pass=True, counts_in_cgpa=True, counts_as_completed=True),
    GradeDefinition(grade="A", points=4.00, rank=2, is_pass=True, counts_in_cgpa=True, counts_as_completed=True),
    GradeDefinition(grade="A-", points=3.67, rank=3, is_pass=True, counts_in_cgpa=True, counts_as_completed=True),
    GradeDefinition(grade="B+", points=3.33, rank=4, is_pass=True, counts_in_cgpa=True, counts_as_completed=True),
    GradeDefinition(grade="B", points=3.00, rank=5, is_pass=True, counts_in_cgpa=True, counts_as_completed=True),
    GradeDefinition(grade="B-", points=2.67, rank=6, is_pass=True, counts_in_cgpa=True, counts_as_completed=True),
    GradeDefinition(grade="C+", points=2.33, rank=7, is_pass=True, counts_in_cgpa=True, counts_as_completed=True),
    GradeDefinition(grade="C", points=2.00, rank=8, is_pass=True, counts_in_cgpa=True, counts_as_completed=True),
    GradeDefinition(grade="C-", points=1.67, rank=9, is_pass=False, counts_in_cgpa=True, counts_as_completed=False),
    GradeDefinition(grade="D+", points=1.33, rank=10, is_pass=False, counts_in_cgpa=True, counts_as_completed=False),
    GradeDefinition(grade="D", points=1.00, rank=11, is_pass=False, counts_in_cgpa=True, counts_as_completed=False),
    GradeDefinition(grade="E", points=0.00, rank=12, is_pass=False, counts_in_cgpa=True, counts_as_completed=False),
    GradeDefinition(grade="TD", points=None, rank=None, is_pass=False, counts_in_cgpa=False, counts_as_completed=False),
    GradeDefinition(grade="HL", points=None, rank=None, is_pass=True, counts_in_cgpa=False, counts_as_completed=True),
]


@pytest.fixture
def utm_scale():
    return GradingScale(tenant_id="UTM", definitions=UTM_GRADE_DEFINITIONS)


# =============================================================================
# 1. Exact Fixture Text Test (Requirement 6)
# =============================================================================
def test_utm_slip_fixture_all_6_courses_sem_2_and_png_317(utm_scale):
    """
    Exact fixture lines from user request:
    EXAMINATION RESULT, SEMESTER 2, SESSION 2024/2025,
    SCSE1203, SCSE1224, SCSR1033, PNG 3.17, PNGK 3.28.
    All courses get 'SEM 2 2024/2025', computed semester GPA = 3.17 (no warning).
    """
    fixture_lines = [
        "EXAMINATION RESULT",
        "SEMESTER 2",
        "SESSION 2024/2025",
        "SCSE1203 SOFTWARE ENGINEERING PRINCIPLES A 4.00 3 12.00 L",
        "SCSE1224 ADVANCED PROGRAMMING A 4.00 4 16.00 L",
        "SCSR1033 COMPUTER ORGANIZATION AND ARCHITECTURE C+ 2.33 3 6.99 L",
        "SECP1513 DISCRETE STRUCTURE B 3.00 3 9.00 L",
        "SECD2523 DATABASE B 3.00 3 9.00 L",
        "UHMS1182 ETHICS C 2.00 2 4.00 L",
        "PNG 3.17",
        "PNGK 3.28",
        "KK this sem 18 / all sem 32, KD 18 / 34"
    ]

    metadata, courses, unparsed = MalaysianTranscriptParser.parse_transcript_lines(fixture_lines, scale=utm_scale)

    assert len(courses) == 6
    assert unparsed == []

    # All courses get 'SEM 2 2024/2025'
    for c in courses:
        assert c.semester == "SEM 2 2024/2025"

    # Verify summary box extraction
    assert metadata["png"] == 3.17
    assert metadata["pngk"] == 3.28
    assert metadata["kk_this_sem"] == 18
    assert metadata["kk_all_sem"] == 32
    assert metadata["kd_this_sem"] == 18
    assert metadata["kd_all_sem"] == 34

    # Computed semester GPA:
    # (12.00 + 16.00 + 6.99 + 9.00 + 9.00 + 4.00) / 18 = 56.99 / 18 = 3.16611... -> 3.17
    assert metadata["computed_semester_gpa"] == 3.17
    assert metadata.get("gpa_warning") is None
    assert metadata.get("warnings") == []


# =============================================================================
# 2. Missing SESSION line -> semester None + warning (Requirement 1 & 6)
# =============================================================================
def test_utm_slip_missing_session_line_yields_none_semester_and_warning(utm_scale):
    """If SESSION line is missing in header -> semester None + warning 'Semester/session not detected'."""
    fixture_lines = [
        "EXAMINATION RESULT",
        "SEMESTER 2",
        # Missing SESSION line
        "SCSE1203 SOFTWARE ENGINEERING PRINCIPLES A 4.00 3 12.00",
        "SCSE1224 ADVANCED PROGRAMMING A 4.00 4 16.00",
        "SCSR1033 COMPUTER ORGANIZATION AND ARCHITECTURE C+ 2.33 3 6.99",
        "PNG 3.17",
        "PNGK 3.28"
    ]

    metadata, courses, unparsed = MalaysianTranscriptParser.parse_transcript_lines(fixture_lines, scale=utm_scale)

    assert metadata["semester"] is None
    assert metadata["academic_session"] is None
    assert "Semester/session not detected" in metadata["warnings"]

    for c in courses:
        assert c.semester is None
        assert c.warning is not None
        assert "Semester/session not detected" in c.warning


def test_utm_slip_missing_semester_line_yields_none_semester_and_warning(utm_scale):
    """If SEMESTER line is missing in header -> semester None + warning 'Semester/session not detected'."""
    fixture_lines = [
        "EXAMINATION RESULT",
        # Missing SEMESTER line
        "SESSION 2024/2025",
        "SCSE1203 SOFTWARE ENGINEERING PRINCIPLES A 4.00 3 12.00",
        "PNG 3.17"
    ]

    metadata, courses, unparsed = MalaysianTranscriptParser.parse_transcript_lines(fixture_lines, scale=utm_scale)

    assert metadata["semester"] is None
    assert "Semester/session not detected" in metadata["warnings"]
    assert courses[0].semester is None
    assert "Semester/session not detected" in courses[0].warning


# =============================================================================
# 3. ST Column Parsing & Cross-Checks (Requirement 2)
# =============================================================================
def test_st_column_codes_and_cross_checks(utm_scale):
    """
    ST status codes:
    L = Pass, G = Fail, TD = Withdrawn, UM = Repeat course, PK = Special exam.
    Cross-checks L -> is_pass, G -> not is_pass; mismatch -> warning.
    """
    lines = [
        "SEMESTER 1 SESSION 2024/2025",
        # 1. Normal Pass (L)
        "SCSE1203 SOFTWARE ENGINEERING PRINCIPLES A 4.00 3 12.00 L",
        # 2. Mismatch: L status on grade E (Fail) -> discrepancy warning
        "SCSE1224 ADVANCED PROGRAMMING E 0.00 4 0.00 L",
        # 3. Normal Fail (G)
        "SCSR1033 COMPUTER ORGANIZATION AND ARCHITECTURE E 0.00 3 0.00 G",
        # 4. Mismatch: G status on grade A (Pass) -> discrepancy warning
        "SECP1513 DISCRETE STRUCTURE A 4.00 3 12.00 G",
        # 5. UM -> Repeat course warning flag
        "SECD2523 DATABASE B 3.00 3 9.00 UM",
        # 6. PK -> Special exam warning
        "UHMS1182 ETHICS B+ 3.33 2 6.66 PK",
        # 7. TD -> status Withdrawn
        "SCSE2013 ALGORITHMS TD 0.00 3 0.00 TD"
    ]

    _, courses, _ = MalaysianTranscriptParser.parse_transcript_lines(lines, scale=utm_scale)

    # 1. Normal L
    c_l = courses[0]
    assert c_l.status == "Passed"
    assert c_l.warning is None

    # 2. Mismatch L on E
    c_l_mismatch = courses[1]
    assert c_l_mismatch.status == "Failed"
    assert c_l_mismatch.warning is not None
    assert "Discrepancy" in c_l_mismatch.warning
    assert "'L' indicates PASS" in c_l_mismatch.warning

    # 3. Normal G
    c_g = courses[2]
    assert c_g.status == "Failed"
    assert c_g.warning is None

    # 4. Mismatch G on A
    c_g_mismatch = courses[3]
    assert c_g_mismatch.status == "Passed"
    assert c_g_mismatch.warning is not None
    assert "Discrepancy" in c_g_mismatch.warning
    assert "'G' indicates FAIL" in c_g_mismatch.warning

    # 5. UM -> repeat course warning
    c_um = courses[4]
    assert c_um.status == "Passed"
    assert c_um.warning is not None
    assert "Repeat course (UM)" in c_um.warning

    # 6. PK -> special exam warning
    c_pk = courses[5]
    assert c_pk.status == "Passed"
    assert c_pk.warning is not None
    assert "Special exam" in c_pk.warning

    # 7. TD -> status Withdrawn
    c_td = courses[6]
    assert c_td.status == "Withdrawn"


# =============================================================================
# 4. Summary Box & GPA Mismatch Detection (Requirement 3)
# =============================================================================
def test_gpa_mismatch_warning_when_computed_differs_from_printed(utm_scale):
    """If computed semester GPA differs from printed PNG by > 0.01 -> warning attached."""
    fixture_lines = [
        "SEMESTER 2 SESSION 2024/2025",
        "SCSE1203 SOFTWARE ENGINEERING PRINCIPLES A 4.00 3 12.00 L",
        "SCSE1224 ADVANCED PROGRAMMING A 4.00 4 16.00 L",
        "SCSR1033 COMPUTER ORGANIZATION AND ARCHITECTURE C+ 2.33 3 6.99 L",
        # Computed GPA for these 3 courses is (12 + 16 + 6.99) / 10 = 3.50.
        # Transcript prints PNG 3.17 -> mismatch difference is 0.33 > 0.01!
        "PNG 3.17",
        "PNGK 3.28"
    ]

    metadata, courses, _ = MalaysianTranscriptParser.parse_transcript_lines(fixture_lines, scale=utm_scale)

    assert metadata["computed_semester_gpa"] == 3.50
    assert metadata["png"] == 3.17
    assert metadata.get("gpa_warning") is not None
    assert "GPA mismatch with transcript (computed 3.50 vs printed 3.17)" in metadata["gpa_warning"]
    assert metadata["gpa_warning"] in metadata["warnings"]


def test_code_and_punctuated_name_on_one_line_then_tokens(utm_scale):
    """Slip layout: 'CODE<nbsp>NAME' line (name with hyphen etc.), then GR/MN/KR/JMN/ST on own lines."""
    fixture_lines = [
        "SEMESTER 2 SESSION 2025/2026",
        "SCSM2223\xa0 \xa0CROSS-PLATFORM APPLICATION DEVELOPMENT",
        "A", "4.00", "3", "12.00", "L",
        "SCSX1013 R&D, ETHICS (I/O) & DR. O'NEIL'S LAB",
        "B", "3.00", "3", "9.00", "L",
    ]

    _, courses, unparsed = MalaysianTranscriptParser.parse_transcript_lines(fixture_lines, scale=utm_scale)

    assert unparsed == []
    assert [(c.course_code, c.course_name, c.grade, c.credits) for c in courses] == [
        ("SCSM2223", "Cross-Platform Application Development", "A", 3),
        ("SCSX1013", "R&D, Ethics (I/O) & Dr. O'Neil'S Lab", "B", 3),
    ]


# =============================================================================
# 5. finalize-approval Endpoint: missing semester/session -> 422 (Requirement 5)
# =============================================================================
def test_finalize_approval_missing_semester_yields_422():
    """Missing semester in finalize-approval returns HTTP 422 without fallback."""
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "email": "advisor@utm.edu.my",
        "sub": "mock-advisor-uid",
        "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"}
    }
    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "A24CS0001",
        "advisor_id": "STAFF-001",
        "academic_session": "2024/2025",
        # Missing semester: None
        "semester": None,
        "courses": [{"course_code": "SECJ1013", "grade": "A", "credit_hour": 3}]
    }

    response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422
    assert "Missing required semester or academic_session" in response.json()["detail"]


def test_finalize_approval_missing_session_yields_422():
    """Missing academic_session in finalize-approval returns HTTP 422 without fallback."""
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "email": "advisor@utm.edu.my",
        "sub": "mock-advisor-uid",
        "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"}
    }
    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "A24CS0001",
        "advisor_id": "STAFF-001",
        "academic_session": "",
        "semester": 1,
        "courses": [{"course_code": "SECJ1013", "grade": "A", "credit_hour": 3}]
    }

    response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422
    assert "Missing required semester or academic_session" in response.json()["detail"]


# =============================================================================
# 6. finalize-approval CGPA comparison with PNGK (Requirement 3)
# =============================================================================
def test_finalize_approval_cgpa_mismatch_with_pngk(utm_scale):
    """In finalize-approval, compare computed cumulative CGPA to PNGK; include warning on mismatch; never auto-correct."""
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "email": "advisor@utm.edu.my",
        "sub": "mock-advisor-uid",
        "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"}
    }
    mock_supabase = MagicMock()
    mock_catalog = {
        "SECJ1013": {"course_code": "SECJ1013", "prerequisites": {"type": "AND", "courses": []}}
    }
    mock_student = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "matric_number": "A24CS0001",
        "student_name": "Test Student"
    }

    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "A24CS0001",
        "advisor_id": "STAFF-001",
        "academic_session": "2024/2025",
        "semester": 1,
        # Grade A gives CGPA 4.00, but printed PNGK is 3.28 -> mismatch!
        "pngk": 3.28,
        "courses": [{"course_code": "SECJ1013", "grade": "A", "credit_hour": 3}]
    }

    patch_target = "app.v1.endpoints.audit.supabase_svc" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.supabase_svc"
    patch_id_target = "app.v1.endpoints.audit._check_advisor_identity" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit._check_advisor_identity"
    patch_scale_target = "app.v1.endpoints.audit.load_scale" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.load_scale"
    with patch(patch_target) as mock_svc, patch(patch_id_target) as mock_check_id, patch(patch_scale_target, return_value=utm_scale):
        mock_svc.get_template_course_catalog.return_value = mock_catalog
        mock_svc.get_or_create_student.return_value = mock_student
        mock_svc.persist_audit_results.return_value = "audit-uuid-test"
        mock_svc.get_student_block_exempted_credits.return_value = (0, None)
        mock_svc.client = mock_supabase

        response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()

        # Warning included
        assert data.get("warning") is not None
        assert "CGPA mismatch with transcript (computed 4.00 vs printed 3.28)" in data["warning"]
        # Never auto-correct: CGPA remains computed 4.00
        assert data["summary"]["cgpa"] == 4.00
