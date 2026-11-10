"""
Unit and Integration Tests for Academic Records Multi-Attempt & Normalization Fix.
Validates:
1. normalize_semester() handles all variations and rejects invalid formats with raw label.
2. Retakes across semesters (e.g. D in Sem 1, B in Sem 3) store 2 distinct rows in academic_records.
3. CGPA correctly follows repeat_policy ('latest' vs 'best').
4. Re-approving the same semester updates rather than duplicates (and dedupes in batch upsert).
5. Audit display shows only the single chosen attempt per course.
6. Unknown grade or unnormalisable semester raises HTTP 422 with the exact message.
"""

import sys
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.auth import verify_advisor_jwt
    from app.schemas.audit import ParsedLineItem, CourseAuditResult, AuditSummary
    from app.engine.grading import (
        GradingScale,
        GradeDefinition,
        normalize_semester,
        compute_cgpa,
        select_attempts_by_repeat_policy
    )
    from app.engine.graph_resolver import PrerequisiteGraphResolver
    from app.v1.endpoints.audit import fetch_and_merge_historical_records
    from app.core.supabase_client import SupabaseService, ExemptionConflictError
except ImportError:
    from backend.app.main import app
    from backend.app.core.auth import verify_advisor_jwt
    from backend.app.schemas.audit import ParsedLineItem, CourseAuditResult, AuditSummary
    from backend.app.engine.grading import (
        GradingScale,
        GradeDefinition,
        normalize_semester,
        compute_cgpa,
        select_attempts_by_repeat_policy
    )
    from backend.app.engine.graph_resolver import PrerequisiteGraphResolver
    from backend.app.v1.endpoints.audit import fetch_and_merge_historical_records
    from backend.app.core.supabase_client import SupabaseService, ExemptionConflictError

client = TestClient(app)

app.dependency_overrides[verify_advisor_jwt] = lambda: {
    "email": "advisor@utm.my",
    "sub": "mock-advisor-uid",
    "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"}
}

AUTH_HEADERS = {"Authorization": "Bearer mock-token"}


@pytest.fixture
def utm_test_scale():
    return GradingScale("UTM", [
        GradeDefinition("A+", 4.00, 1, True, True, True),
        GradeDefinition("A",  4.00, 2, True, True, True),
        GradeDefinition("A-", 3.67, 3, True, True, True),
        GradeDefinition("B+", 3.33, 4, True, True, True),
        GradeDefinition("B",  3.00, 5, True, True, True),
        GradeDefinition("B-", 2.67, 6, True, True, True),
        GradeDefinition("C+", 2.33, 7, True, True, True),
        GradeDefinition("C",  2.00, 8, True, True, True),
        GradeDefinition("C-", 1.67, 9, True, True, True),
        GradeDefinition("D+", 1.33, 10, True, True, True),
        GradeDefinition("D",  1.00, 11, False, True, False),
        GradeDefinition("D-", 0.67, 12, False, True, False),
        GradeDefinition("E",  0.00, 13, False, True, False),
        GradeDefinition("HL", None, None, True, False, True),
        GradeDefinition("EX", None, None, True, False, True),
    ])


@pytest.fixture(autouse=True)
def mock_load_scale_autouse(utm_test_scale):
    targets = [
        t for t in ["app.v1.endpoints.audit.load_scale", "backend.app.v1.endpoints.audit.load_scale"]
        if t.rsplit(".", 1)[0] in sys.modules
    ]
    if not targets:
        targets = ["backend.app.v1.endpoints.audit.load_scale"]

    with patch(targets[0], return_value=utm_test_scale):
        if len(targets) > 1:
            with patch(targets[1], return_value=utm_test_scale):
                yield
        else:
            yield


# =============================================================================
# 1. Tests: Semester Label Normalization & Test Table
# =============================================================================
def test_production_semester_values_normalise_identically():
    """Current distinct semester values in production: 'Sem 1 2024/2025' and 'Sem 2 2024/2025'."""
    assert normalize_semester("Sem 1 2024/2025") == "SEM 1 2024/2025"
    assert normalize_semester("Sem 2 2024/2025") == "SEM 2 2024/2025"


def test_test_table_labels_matching_sql_verification_suite():
    """
    Runs the exact test table of labels defined in migration 27 through Python normalize_semester.
    Verifies identical output and rejection behavior to the SQL function.
    """
    test_cases = [
        # (input_label, expected_output, should_succeed)
        ("Sem 1 2024/2025", "SEM 1 2024/2025", True),
        ("Sem 2 2024/2025", "SEM 2 2024/2025", True),
        ("SEM 1 2024/25", "SEM 1 2024/2025", True),
        ("Semester 1 2024/2025", "SEM 1 2024/2025", True),
        ("SEMESTER 1 SESSION 2024/2025", "SEM 1 2024/2025", True),
        ("SEM: 2, 2023/2024", "SEM 2 2023/2024", True),
        ("2024/2025-1", "SEM 1 2024/2025", True),
        ("2024/2025 1", "SEM 1 2024/2025", True),
        ("2024/2025/1", "SEM 1 2024/2025", True),
        ("2024/25-2", "SEM 2 2024/2025", True),
        ("2024/2025-3", "SEM 3 2024/2025", True),
        ("2024/2025-4", "SEM 4 2024/2025", True),
        # Rejected cases (guess fallbacks removed)
        ("FALL TERM 2024", None, False),
        ("Spring 2025", None, False),
        ("Summer 2024", None, False),
        ("2024", None, False),
        ("SEM 1 2024", None, False),
        ("1", None, False),
        ("Sem 1", None, False),
        ("2024/2025", None, False),
        ("Sem 5 2024/2025", None, False),
        ("TERM 1 2024/2025", None, False),
        ("TRIMESTER 2 2024/2025", None, False),
        ("", None, False),
        ("   ", None, False),
    ]

    for label, expected, should_succeed in test_cases:
        if should_succeed:
            actual = normalize_semester(label)
            assert actual == expected, f"Failed for '{label}': got '{actual}', expected '{expected}'"
        else:
            with pytest.raises(ValueError) as excinfo:
                normalize_semester(label)
            # Fail loud: raw label must be in error message
            assert label in str(excinfo.value) or "empty" in str(excinfo.value).lower(), (
                f"Raw label '{label}' missing from error message: {excinfo.value}"
            )


# =============================================================================
# 2. Tests: Retake (D in Sem 1, B in Sem 3) stores 2 rows and CGPA follows repeat_policy
# =============================================================================
def test_retake_stores_2_rows_and_cgpa_follows_repeat_policy(utm_test_scale):
    """
    Course SECJ1013 (3 credits):
    Attempt 1: Sem 1 (Grade D, 1.00 points)
    Attempt 2: Sem 3 (Grade B, 3.00 points)
    1. Persist audit stores both rows in academic_records with on_conflict composite key.
    2. CGPA follows repeat_policy:
       - 'latest': selects Sem 3 (B, 3.00) -> CGPA = 3.00
       - 'best': selects Sem 3 (B, 3.00) -> CGPA = 3.00
    """
    rec_attempt1 = ParsedLineItem(
        course_code="SECJ1013",
        course_name="Programming Technique I",
        credits=3,
        grade="D",
        grade_point=1.00,
        semester="Sem 1 2023/2024",
        status="Failed"
    )
    rec_attempt2 = ParsedLineItem(
        course_code="SECJ1013",
        course_name="Programming Technique I",
        credits=3,
        grade="B",
        grade_point=3.00,
        semester="Sem 3 2023/2024",
        status="Passed"
    )

    # 1. Test compute_cgpa with repeat_policy
    cgpa_latest = compute_cgpa([rec_attempt1, rec_attempt2], utm_test_scale, repeat_policy="latest")
    assert cgpa_latest == 3.00

    cgpa_best = compute_cgpa([rec_attempt1, rec_attempt2], utm_test_scale, repeat_policy="best")
    assert cgpa_best == 3.00

    # Test reverse chronology (Grade B first in Sem 1, Grade D later in Sem 3)
    rec_b_sem1 = ParsedLineItem(course_code="SECJ1013", course_name="Prog I", credits=3, grade="B", grade_point=3.00, semester="Sem 1 2023/2024", status="Passed")
    rec_d_sem3 = ParsedLineItem(course_code="SECJ1013", course_name="Prog I", credits=3, grade="D", grade_point=1.00, semester="Sem 3 2023/2024", status="Failed")

    cgpa_rev_latest = compute_cgpa([rec_b_sem1, rec_d_sem3], utm_test_scale, repeat_policy="latest")
    assert cgpa_rev_latest == 1.00  # Sem 3 was latest, so D is chosen

    cgpa_rev_best = compute_cgpa([rec_b_sem1, rec_d_sem3], utm_test_scale, repeat_policy="best")
    assert cgpa_rev_best == 3.00  # Grade B had higher points, so B is chosen

    # 2. Test audit_student_records display filtering vs all attempts
    catalog = {"SECJ1013": {"course_code": "SECJ1013", "prerequisites": {"type": "AND", "courses": []}}}
    display_results, summary, all_attempts = PrerequisiteGraphResolver.audit_student_records(
        records=[rec_attempt1, rec_attempt2],
        course_catalog=catalog,
        scale=utm_test_scale,
        total_required_credits=130,
        repeat_policy="latest",
        return_all_attempts=True
    )
    # Display results contains only 1 chosen attempt for SECJ1013
    assert len(display_results) == 1
    assert display_results[0].grade == "B"
    assert display_results[0].semester == "Sem 3 2023/2024"

    # All attempts contains both evaluated attempts for persistence
    assert len(all_attempts) == 2

    # 3. Test persistence upserts 2 distinct rows
    mock_supabase = MagicMock()
    mock_svc = SupabaseService()
    mock_svc.client = mock_supabase

    audit_summary = summary
    with patch.object(mock_svc, "_ensure_ready"):
        mock_svc.persist_audit_results(
            matric_no="A20EC0001",
            advisor_id="STAFF-001",
            records=all_attempts,
            summary=audit_summary,
            storage_pdf_path="doc:123",
            tenant_id="UTM"
        )

        mock_supabase.table.assert_any_call("academic_records")
        upsert_call = mock_supabase.table("academic_records").upsert.call_args
        records_upserted = upsert_call[0][0]
        on_conflict = upsert_call[1]["on_conflict"]

        # 4-column composite key used
        assert on_conflict == "tenant_id,matric_no,course_code,semester"
        # 2 distinct rows upserted because semesters differ
        assert len(records_upserted) == 2
        semesters = {r["semester"] for r in records_upserted}
        assert semesters == {"SEM 1 2023/2024", "SEM 3 2023/2024"}


# =============================================================================
# 3. Tests: Re-approving the same semester updates rather than duplicates
# =============================================================================
def test_reapproving_same_semester_updates_rather_than_duplicates():
    """
    When approving a semester already present in academic_records:
    1. fetch_and_merge_historical_records matches on (course_code, normalised semester)
       and replaces the existing record with the new record.
    2. Other semesters remain untouched.
    """
    existing_db_rows = [
        {
            "tenant_id": "UTM",
            "matric_no": "A20EC0001",
            "course_code": "SECJ1013",
            "course_name": "Programming Technique I",
            "credits": 3,
            "grade": "C",
            "grade_point": 2.00,
            "semester": "SEM 1 2024/2025",
            "status": "Passed"
        },
        {
            "tenant_id": "UTM",
            "matric_no": "A20EC0001",
            "course_code": "SECJ1023",
            "course_name": "Programming Technique II",
            "credits": 3,
            "grade": "A",
            "grade_point": 4.00,
            "semester": "SEM 2 2024/2025",
            "status": "Passed"
        }
    ]

    mock_supabase = MagicMock()
    query_mock = MagicMock()
    mock_supabase.table.return_value = query_mock
    query_mock.select.return_value = query_mock
    query_mock.eq.return_value = query_mock
    query_mock.execute.return_value = MagicMock(data=existing_db_rows)

    fetch_and_merge_historical_records.__globals__["supabase_svc"].client = mock_supabase

    # Advisor re-approves Sem 1 with updated grade A (using a variant semester label "Sem 1 2024/2025")
    new_records = [
        ParsedLineItem(
            course_code="SECJ1013",
            course_name="Programming Technique I",
            credits=3,
            grade="A",
            grade_point=4.00,
            semester="Sem 1 2024/2025",  # variant label that normalizes to "SEM 1 2024/2025"
            status="Passed"
        )
    ]

    merged = fetch_and_merge_historical_records("A20EC0001", new_records, tenant_id="UTM")

    # Total records should be 2, NOT 3 (SECJ1013 is replaced, not duplicated)
    assert len(merged) == 2
    secj1013 = [r for r in merged if r.course_code == "SECJ1013"]
    assert len(secj1013) == 1
    assert secj1013[0].grade == "A"
    assert secj1013[0].grade_point == 4.00

    # Sem 2 SECJ1023 was preserved
    secj1023 = [r for r in merged if r.course_code == "SECJ1023"]
    assert len(secj1023) == 1
    assert secj1023[0].semester == "SEM 2 2024/2025"


def test_zero_credit_record_stays_zero_after_later_approval():
    """A saved HL (pass, 0 credits) record keeps credits 0 when a later semester is approved."""
    existing_db_rows = [{
        "tenant_id": "UTM", "matric_no": "A20EC0001", "course_code": "UHLB1112",
        "course_name": "Co-curriculum", "credits": 0, "grade": "HL", "grade_point": 0.0,
        "semester": "SEM 1 2024/2025", "status": "Passed",
    }]
    mock_supabase = MagicMock()
    q = MagicMock()
    mock_supabase.table.return_value = q
    q.select.return_value = q
    q.eq.return_value = q
    q.execute.return_value = MagicMock(data=existing_db_rows)
    fetch_and_merge_historical_records.__globals__["supabase_svc"].client = mock_supabase

    new_records = [ParsedLineItem(course_code="SECJ1023", course_name="PT II", credits=3,
                                  grade="A", grade_point=4.0, semester="SEM 2 2024/2025", status="Passed")]
    merged = fetch_and_merge_historical_records("A20EC0001", new_records, tenant_id="UTM")
    hl = [r for r in merged if r.course_code == "UHLB1112"]
    assert len(hl) == 1 and hl[0].credits == 0

    existing_db_rows[0]["credits"] = None
    with pytest.raises(ValueError):
        fetch_and_merge_historical_records("A20EC0001", new_records, tenant_id="UTM")


def test_persist_audit_results_dedupes_batch_on_course_and_semester():
    """
    If a batch sent to persist_audit_results contains duplicates for (course_code, semester)
    due to varied formatting, persist_audit_results dedupes keeping the later record.
    """
    mock_supabase = MagicMock()
    mock_svc = SupabaseService()
    mock_svc.client = mock_supabase

    batch = [
        CourseAuditResult(
            course_code="SECJ1013",
            course_name="Prog I",
            credits=3,
            grade="C",
            grade_point=2.00,
            semester="Sem 1 2024/2025",
            status="Passed",
            traffic_light="GREEN",
            prerequisite_met=True
        ),
        CourseAuditResult(
            course_code="SECJ1013",
            course_name="Prog I",
            credits=3,
            grade="A",
            grade_point=4.00,
            semester="SEM 1 2024/25",  # Same canonical semester
            status="Passed",
            traffic_light="GREEN",
            prerequisite_met=True
        )
    ]

    summary = AuditSummary(cgpa=4.0, total_credits_earned=3)

    with patch.object(mock_svc, "_ensure_ready"):
        mock_svc.persist_audit_results(
            matric_no="A20EC0001",
            advisor_id="STAFF-001",
            records=batch,
            summary=summary,
            storage_pdf_path="doc:123",
            tenant_id="UTM"
        )

        upsert_call = mock_supabase.table("academic_records").upsert.call_args
        records_upserted = upsert_call[0][0]
        # Deduped to 1 row, keeping the later one (grade A)
        assert len(records_upserted) == 1
        assert records_upserted[0]["grade"] == "A"
        assert records_upserted[0]["semester"] == "SEM 1 2024/2025"


def _persist_over_exemption(batch_grade):
    client = MagicMock()
    q = client.table.return_value
    for m in ("select", "eq", "in_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[{"course_code": "SECJ1013", "semester": "SEM 1 2024/2025", "grade": "EX"}])
    svc = SupabaseService()
    svc.client = client
    record = CourseAuditResult(course_code="SECJ 1013", course_name="Prog I", credits=3, grade=batch_grade, grade_point=0.0, prerequisite_met=True,
                               semester="Sem 1 2024/25", status="Passed", traffic_light="GREEN")
    with patch.object(svc, "_ensure_ready"):
        svc.persist_audit_results(matric_no="A1", advisor_id="S1", records=[record],
                                  summary=AuditSummary(cgpa=4.0), storage_pdf_path="doc:1", tenant_id="UTM")
    return q


def test_persist_refuses_to_overwrite_exemption():
    with pytest.raises(ExemptionConflictError, match="Course SECJ1013 has an exemption in that semester — remove it first"):
        _persist_over_exemption("A")


def test_persist_allows_same_exemption_in_merged_history():
    q = _persist_over_exemption("EX")
    q.upsert.assert_called_once()


def test_finalize_maps_exemption_conflict_to_409():
    import asyncio
    audit_ep = sys.modules[fetch_and_merge_historical_records.__module__]
    from fastapi import HTTPException
    svc = MagicMock()
    svc.client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    svc.get_template_course_catalog.return_value = {}
    svc.get_student_block_exempted_credits.return_value = (0, 130)
    svc.persist_audit_results.side_effect = ExemptionConflictError("Course SECJ1013 has an exemption in that semester — remove it first")
    scale = GradingScale("UTM", [GradeDefinition("A", 4.0, 1, True, True, True)])
    request = audit_ep.FinalizeApprovalRequest(
        document_id="doc-1", matric_number="A1", academic_session="2024/2025", semester=1,
        courses=[{"course_code": "SECJ1013", "course_name": "P", "grade": "A", "credits": 3, "credit_hour": 3, "status": "Pass"}],
    )
    with patch.object(audit_ep, "supabase_svc", svc), patch.object(audit_ep, "load_scale", return_value=scale), \
            patch.object(audit_ep, "_load_repeat_policy", return_value="latest"), \
            patch.object(audit_ep, "_extract_advisor_id", return_value="S1"), \
            patch.object(audit_ep, "_extract_tenant_id", return_value="UTM"), \
            patch.object(audit_ep, "_load_authorized_document"):
        with pytest.raises(HTTPException) as e:
            asyncio.run(audit_ep.finalize_approval(request, {"sub": "u1"}))
    assert e.value.status_code == 409
    assert "remove it first" in e.value.detail


# =============================================================================
# 4. Tests: Unknown Grade & Invalid Semester -> HTTP 422
# =============================================================================
def test_finalize_approval_unknown_grade_returns_422():
    """Submitting a grade unknown to the tenant grading scale returns HTTP 422 with the error detail."""
    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "A20EC0001",
        "student_name": "Test Student",
        "academic_session": "2024/2025",
        "semester": 1,
        "courses": [
            {
                "course_code": "SECJ1013",
                "course_name": "Programming Technique I",
                "grade": "INVALID_GRADE_XYZ",
                "credit_hour": 3,
                "credits": 3,
                "status": "Pass"
            }
        ]
    }
    response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    assert "Unknown grade 'INVALID_GRADE_XYZ'" in data["detail"]


def test_finalize_approval_invalid_semester_returns_422():
    """Submitting an unnormalisable semester label in finalize-approval returns HTTP 422 with raw label."""
    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "A20EC0001",
        "student_name": "Test Student",
        "academic_session": "2024/2025",
        "semester": 1,
        "courses": [
            {
                "course_code": "SECJ1013",
                "course_name": "Programming Technique I",
                "grade": "A",
                "credit_hour": 3,
                "credits": 3,
                "session_semester": "BAD_SEMESTER_LABEL_123"
            }
        ]
    }
    response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    assert "BAD_SEMESTER_LABEL_123" in data["detail"]
