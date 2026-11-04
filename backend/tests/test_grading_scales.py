"""
Unit and integration tests for per-university grading scales, exemptions,
fail-loud unknown grade handling, repeat policies, and exemption endpoint security.
"""

from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.auth import verify_advisor_jwt
    from app.engine.grading import (
        GradingScale,
        GradeDefinition,
        load_scale,
        compute_cgpa,
        compute_completed_credits,
    )
    from app.engine.parsers.malaysian_regex import MalaysianTranscriptParser
    from app.schemas.audit import ParsedLineItem
except ImportError:
    from backend.app.main import app
    from backend.app.core.auth import verify_advisor_jwt
    from backend.app.engine.grading import (
        GradingScale,
        GradeDefinition,
        load_scale,
        compute_cgpa,
        compute_completed_credits,
    )
    from backend.app.engine.parsers.malaysian_regex import MalaysianTranscriptParser
    from backend.app.schemas.audit import ParsedLineItem

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures & Test Scale Setup
# ---------------------------------------------------------------------------
@pytest.fixture
def utm_fixture_scale():
    """
    Active verbatim UTM grading scale matching Migration 26:
    18 rows from A+ (4.00) down to TS.
    D+ (1.33) passes.
    D (1.00) and D- (0.67) fail (is_pass=False, counts_as_completed=False).
    """
    defs = [
        GradeDefinition("A+", 4.00, 1, True, True, True, min_mark=90, max_mark=100, achievement_label="Excellent Pass"),
        GradeDefinition("A",  4.00, 2, True, True, True, min_mark=80, max_mark=89,  achievement_label="Excellent Pass"),
        GradeDefinition("A-", 3.67, 3, True, True, True, min_mark=75, max_mark=79,  achievement_label="Excellent Pass"),
        GradeDefinition("B+", 3.33, 4, True, True, True, min_mark=70, max_mark=74,  achievement_label="Good Pass"),
        GradeDefinition("B",  3.00, 5, True, True, True, min_mark=65, max_mark=69,  achievement_label="Good Pass"),
        GradeDefinition("B-", 2.67, 6, True, True, True, min_mark=60, max_mark=64,  achievement_label="Good Pass"),
        GradeDefinition("C+", 2.33, 7, True, True, True, min_mark=55, max_mark=59,  achievement_label="Pass"),
        GradeDefinition("C",  2.00, 8, True, True, True, min_mark=50, max_mark=54,  achievement_label="Pass"),
        GradeDefinition("C-", 1.67, 9, True, True, True, min_mark=45, max_mark=49,  achievement_label="Pass"),
        GradeDefinition("D+", 1.33, 10, True, True, True, min_mark=40, max_mark=44, achievement_label="Minimum Pass"),
        GradeDefinition("D",  1.00, 11, False, True, False, min_mark=35, max_mark=39, achievement_label="Fail"),
        GradeDefinition("D-", 0.67, 12, False, True, False, min_mark=30, max_mark=34, achievement_label="Fail"),
        GradeDefinition("E",  0.00, 13, False, True, False, min_mark=0,  max_mark=29, achievement_label="Fail"),
        GradeDefinition("HL", None, None, True, False, True, achievement_label="Pass (non-graded)"),
        GradeDefinition("EX", None, None, True, False, True, achievement_label="Exempted"),
        GradeDefinition("CT", None, None, True, False, True, achievement_label="Credit Transfer"),
        GradeDefinition("TD", None, None, False, False, False, achievement_label="Withdrawn"),
        GradeDefinition("TS", None, None, False, False, False, achievement_label="Incomplete"),
    ]
    return GradingScale("UTM", defs)


@pytest.fixture
def fake_second_tenant_scale():
    defs = [
        GradeDefinition("A",  4.00, 1, True, True, True),
        GradeDefinition("A-", 3.70, 2, True, True, True),
        GradeDefinition("B+", 3.50, 3, True, True, True),
        GradeDefinition("B",  3.00, 4, True, True, True),
        GradeDefinition("B-", 2.70, 5, True, True, True),
        GradeDefinition("C+", 2.30, 6, True, True, True),
        GradeDefinition("C",  2.00, 7, True, True, True),
        GradeDefinition("D",  1.00, 8, False, True, False),
        GradeDefinition("E",  0.00, 9, False, True, False),
        GradeDefinition("EX", None, None, True, False, True),
        GradeDefinition("CT", None, None, True, False, True),
    ]
    return GradingScale("TENANT_SECOND", defs)


# ---------------------------------------------------------------------------
# Test: Missing tenant scale raises ValueError
# ---------------------------------------------------------------------------
def test_missing_tenant_scale_raises():
    mock_client = MagicMock()
    mock_client.table().select().or_().execute.return_value = MagicMock(data=[])

    with pytest.raises(ValueError) as exc:
        load_scale("UNKNOWN_TENANT_XYZ", client=mock_client)
    assert "No grading scale found for tenant 'UNKNOWN_TENANT_XYZ'" in str(exc.value)


# ---------------------------------------------------------------------------
# Test: UTM scale pass/fail rules for D+, D, D-
# ---------------------------------------------------------------------------
def test_utm_pass_fail_rules(utm_fixture_scale):
    # D+ passes
    assert utm_fixture_scale.is_pass("D+") is True
    assert utm_fixture_scale.counts_as_completed("D+") is True
    assert utm_fixture_scale.grade_points("D+") == 1.33

    # D fails
    assert utm_fixture_scale.is_pass("D") is False
    assert utm_fixture_scale.counts_as_completed("D") is False
    assert utm_fixture_scale.grade_points("D") == 1.00

    # D- fails
    assert utm_fixture_scale.is_pass("D-") is False
    assert utm_fixture_scale.counts_as_completed("D-") is False
    assert utm_fixture_scale.grade_points("D-") == 0.67


# ---------------------------------------------------------------------------
# Test: Unknown grade or min_grade raises ValueError (fail loud)
# ---------------------------------------------------------------------------
def test_unknown_grade_raises_fail_loud(utm_fixture_scale):
    with pytest.raises(ValueError) as exc1:
        utm_fixture_scale.grade_points("Z+", "SECJ2013")
    assert "Unknown grade 'Z+' for course 'SECJ2013'" in str(exc1.value)

    with pytest.raises(ValueError) as exc2:
        utm_fixture_scale.is_pass("INVENTED", "MATH101")
    assert "Unknown grade 'INVENTED' for course 'MATH101'" in str(exc2.value)

    with pytest.raises(ValueError) as exc3:
        utm_fixture_scale.meets_min_grade("C", "UNKNOWN_REQ", "SECJ1013")
    assert "Unknown grade 'UNKNOWN_REQ' for course 'SECJ1013'" in str(exc3.value)

    with pytest.raises(ValueError) as exc4:
        utm_fixture_scale.meets_min_grade("UNKNOWN_GRADE", "C", "SECJ1013")
    assert "Unknown grade 'UNKNOWN_GRADE' for course 'SECJ1013'" in str(exc4.value)


# ---------------------------------------------------------------------------
# Test: No code path references lowercase "utm"
# ---------------------------------------------------------------------------
def test_no_code_path_references_utm():
    """Verify that backend/app/engine/ contains zero references to lowercase 'utm'."""
    engine_dir = Path(__file__).resolve().parent.parent / "app" / "engine"
    assert engine_dir.is_dir(), f"Engine directory {engine_dir} not found"

    py_files = list(engine_dir.glob("**/*.py"))
    assert len(py_files) > 0

    violations = []
    for f in py_files:
        content = f.read_text(encoding="utf-8")
        # Check for lowercase 'utm' string literal or identifiers
        for line_no, line in enumerate(content.splitlines(), start=1):
            if '"utm"' in line or "'utm'" in line or 'get_default_scale' in line:
                violations.append(f"{f.name}:{line_no} -> {line.strip()}")

    assert not violations, f"Found hardcoded 'utm' references in engine:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# Test: EX/CT count as completed but not in CGPA; block credits add to total
# ---------------------------------------------------------------------------
def test_exemptions_and_block_credits_math(utm_fixture_scale):
    records = [
        {"course_code": "SECJ1013", "grade": "A", "credits": 3, "semester": "Sem 1"},
        {"course_code": "SECJ1023", "grade": "B", "credits": 3, "semester": "Sem 1"},
        {"course_code": "UHMS1182", "grade": "EX", "credits": 2, "semester": "Sem 1"},
        {"course_code": "SECP1513", "grade": "CT", "credits": 3, "semester": "Sem 1"},
    ]

    calculated_cgpa = compute_cgpa(records, utm_fixture_scale)
    assert calculated_cgpa == 3.50

    completed_without_block = compute_completed_credits(records, utm_fixture_scale, block_exempted_credits=0)
    assert completed_without_block == 11

    completed_with_block = compute_completed_credits(records, utm_fixture_scale, block_exempted_credits=30)
    assert completed_with_block == 41

    assert compute_cgpa(records, utm_fixture_scale) == 3.50


# ---------------------------------------------------------------------------
# Test: Repeat policy latest vs best
# ---------------------------------------------------------------------------
def test_repeat_policy_latest_vs_best(utm_fixture_scale):
    records_worse = [
        {"course_code": "SECJ1013", "grade": "B", "credits": 3, "semester": "Sem 1 2022/2023"},
        {"course_code": "SECJ1013", "grade": "C", "credits": 3, "semester": "Sem 2 2022/2023"},
    ]
    assert compute_cgpa(records_worse, utm_fixture_scale, repeat_policy="latest") == 2.00
    assert compute_cgpa(records_worse, utm_fixture_scale, repeat_policy="best") == 3.00

    records_improved = [
        {"course_code": "SECD2523", "grade": "D", "credits": 3, "semester": "Sem 1 2022/2023"},
        {"course_code": "SECD2523", "grade": "A", "credits": 3, "semester": "Sem 2 2022/2023"},
    ]
    assert compute_cgpa(records_improved, utm_fixture_scale, repeat_policy="latest") == 4.00
    assert compute_cgpa(records_improved, utm_fixture_scale, repeat_policy="best") == 4.00


# ---------------------------------------------------------------------------
# Test: meets_min_grade (B- meets C, D+ does not)
# ---------------------------------------------------------------------------
def test_meets_min_grade(utm_fixture_scale):
    assert utm_fixture_scale.meets_min_grade("B-", "C") is True
    assert utm_fixture_scale.meets_min_grade("C+", "C") is True
    assert utm_fixture_scale.meets_min_grade("C", "C") is True
    assert utm_fixture_scale.meets_min_grade("C-", "C") is False
    assert utm_fixture_scale.meets_min_grade("D+", "C") is False
    assert utm_fixture_scale.meets_min_grade("D", "C") is False
    assert utm_fixture_scale.meets_min_grade("D-", "C") is False

    # Neutral passing grades always satisfy prerequisites
    assert utm_fixture_scale.meets_min_grade("EX", "C") is True
    assert utm_fixture_scale.meets_min_grade("CT", "B") is True
    assert utm_fixture_scale.meets_min_grade("HL", "A") is True


# ---------------------------------------------------------------------------
# Test: Status cross-check produces a warning and never auto-corrects
# ---------------------------------------------------------------------------
def test_status_cross_check_warning(utm_fixture_scale):
    transcript_lines = [
        "SEMESTER 1 SESSION 2023/2024",
        "SECJ1013 PROGRAMMING TECHNIQUE I 3 E 0.00 LULUS",
        "SECP1513 DISCRETE STRUCTURE 3 A 4.00 GAGAL",
        "SECR1013 DIGITAL LOGIC 3 A 4.00 LULUS"
    ]

    _, parsed_courses, _ = MalaysianTranscriptParser.parse_transcript_lines(transcript_lines, scale=utm_fixture_scale)

    c1 = next(c for c in parsed_courses if c.course_code == "SECJ1013")
    assert c1.grade == "E"
    assert c1.status == "Failed"
    assert c1.warning is not None
    assert "Discrepancy" in c1.warning
    assert "LULUS" in c1.warning

    c2 = next(c for c in parsed_courses if c.course_code == "SECP1513")
    assert c2.grade == "A"
    assert c2.status == "Passed"
    assert c2.warning is not None
    assert "Discrepancy" in c2.warning
    assert "GAGAL" in c2.warning

    c3 = next(c for c in parsed_courses if c.course_code == "SECR1013")
    assert c3.grade == "A"
    assert c3.status == "Passed"
    assert c3.warning is None


# ---------------------------------------------------------------------------
# Test: Exemptions endpoint security & audit logging
# ---------------------------------------------------------------------------
def _override_jwt(user_id="adv-uuid-1", staff_id="STAFF-UTM-01", tenant_id="UTM"):
    return {
        "sub": user_id,
        "email": "advisor@utm.my",
        "app_metadata": {
            "staff_id": staff_id,
            "tenant_id": tenant_id
        }
    }


def _mock_supabase_for_exemptions(
    student_tenant="UTM",
    assigned_advisor="STAFF-UTM-01",
    caller_staff_id="STAFF-UTM-01",
    caller_tenant="UTM",
    advisor_exists=True,
    student_exists=True
):
    mock_svc = MagicMock()
    mock_client = MagicMock()
    mock_svc.client = mock_client

    inserted_audits = []

    def mock_table(table_name):
        tbl = MagicMock()
        if table_name == "students":
            sel = MagicMock()
            tbl.select.return_value = sel
            student_row = {
                "matric_no": "A24MJ5050",
                "tenant_id": student_tenant,
                "advisor_staff_id": assigned_advisor,
                "entry_semester": 1,
                "block_exempted_credits": 0,
                "cohort_id": "cohort-1"
            }

            def students_eq(col, val):
                # First filter is tenant_id: only the student's own tenant finds the row
                eq_m = MagicMock()
                found = student_exists and col == "tenant_id" and val == student_tenant
                eq_m.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[student_row] if found else []
                )
                return eq_m

            sel.eq.side_effect = students_eq

            upd = MagicMock()
            tbl.update.return_value = upd
            upd.eq.return_value.execute.return_value = MagicMock(data=[{}])

        elif table_name == "advisors":
            sel = MagicMock()
            tbl.select.return_value = sel
            eq_m = MagicMock()
            sel.eq.return_value = eq_m
            adv_data = [{
                "staff_id": caller_staff_id,
                "tenant_id": caller_tenant
            }] if advisor_exists else []
            eq_m.limit.return_value.execute.return_value = MagicMock(data=adv_data)

        elif table_name == "academic_records":
            sel = MagicMock()
            tbl.select.return_value = sel
            eq1 = MagicMock()
            sel.eq.return_value = eq1
            eq2 = MagicMock()
            eq1.eq.return_value = eq2
            eq2.execute.return_value = MagicMock(data=[])
            tbl.upsert.return_value.execute.return_value = MagicMock(data=[{}])
            tbl.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])

        elif table_name == "exemption_audit":
            def mock_insert(rows):
                inserted_audits.extend(rows)
                ret = MagicMock()
                ret.execute.return_value = MagicMock(data=rows)
                return ret
            tbl.insert.side_effect = mock_insert

        return tbl

    mock_client.table.side_effect = mock_table
    mock_svc.get_template_course_catalog.return_value = {"SECJ1013": {"code": "SECJ1013"}}
    return mock_svc, inserted_audits


def test_exemptions_endpoint_forbidden_for_non_advisor():
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "sub": "student-uuid",
        "email": "student@graduate.utm.my",
        "app_metadata": {}
    }
    try:
        with patch("app.v1.endpoints.students.SupabaseService") as m1, patch("backend.app.v1.endpoints.students.SupabaseService", create=True) as m2:
            mock_svc, _ = _mock_supabase_for_exemptions(advisor_exists=False)
            m1.return_value = mock_svc
            m2.return_value = mock_svc

            resp = client.patch(
                "/api/v1/students/A24MJ5050/exemptions",
                json={"entry_semester": 2}
            )
            assert resp.status_code == 403
            assert "not an authorized academic advisor" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(verify_advisor_jwt, None)


def test_exemptions_endpoint_forbidden_for_cross_tenant():
    app.dependency_overrides[verify_advisor_jwt] = lambda: _override_jwt(staff_id="STAFF-UTM-01", tenant_id="UTM")
    try:
        with patch("app.v1.endpoints.students.SupabaseService") as m1, patch("backend.app.v1.endpoints.students.SupabaseService", create=True) as m2:
            mock_svc, _ = _mock_supabase_for_exemptions(
                student_tenant="UKM",
                assigned_advisor="STAFF-UTM-01",
                caller_staff_id="STAFF-UTM-01",
                caller_tenant="UTM"
            )
            m1.return_value = mock_svc
            m2.return_value = mock_svc

            resp = client.patch(
                "/api/v1/students/A24MJ5050/exemptions",
                json={"entry_semester": 2}
            )
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(verify_advisor_jwt, None)


def test_exemptions_endpoint_forbidden_for_unassigned_advisor():
    app.dependency_overrides[verify_advisor_jwt] = lambda: _override_jwt(staff_id="STAFF-UTM-01", tenant_id="UTM")
    try:
        with patch("app.v1.endpoints.students.SupabaseService") as m1, patch("backend.app.v1.endpoints.students.SupabaseService", create=True) as m2:
            mock_svc, _ = _mock_supabase_for_exemptions(
                student_tenant="UTM",
                assigned_advisor="STAFF-UTM-OTHER",
                caller_staff_id="STAFF-UTM-01",
                caller_tenant="UTM"
            )
            m1.return_value = mock_svc
            m2.return_value = mock_svc

            resp = client.patch(
                "/api/v1/students/A24MJ5050/exemptions",
                json={"entry_semester": 2}
            )
            assert resp.status_code == 403
            assert "not the assigned advisor" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(verify_advisor_jwt, None)


def test_exemptions_endpoint_success_and_audit_written():
    app.dependency_overrides[verify_advisor_jwt] = lambda: _override_jwt(staff_id="STAFF-UTM-01", tenant_id="UTM")
    try:
        with patch("app.v1.endpoints.students.SupabaseService") as m1, patch("backend.app.v1.endpoints.students.SupabaseService", create=True) as m2:
            mock_svc, audits = _mock_supabase_for_exemptions(
                student_tenant="UTM",
                assigned_advisor="STAFF-UTM-01",
                caller_staff_id="STAFF-UTM-01",
                caller_tenant="UTM"
            )
            m1.return_value = mock_svc
            m2.return_value = mock_svc

            payload = {
                "entry_semester": 3,
                "block_exempted_credits": 24,
                "course_actions": [
                    {
                        "action": "add",
                        "course_code": "SECJ1013",
                        "grade": "EX",
                        "credits": 3,
                        "course_name": "Programming Technique I"
                    }
                ]
            }

            resp = client.patch("/api/v1/students/A24MJ5050/exemptions", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["entry_semester"] == 3
            assert data["block_exempted_credits"] == 24
            assert data["audits_written"] == 3

            fields_audited = [a["field"] for a in audits]
            assert "entry_semester" in fields_audited
            assert "block_exempted_credits" in fields_audited
            assert "course_exemption_add:SECJ1013" in fields_audited

            for a in audits:
                assert a["tenant_id"] == "UTM"
                assert a["matric_no"] == "A24MJ5050"
                assert a["changed_by_staff_id"] == "STAFF-UTM-01"
    finally:
        app.dependency_overrides.pop(verify_advisor_jwt, None)


@pytest.mark.parametrize("bad_credits", [None, -1])
def test_exemptions_endpoint_rejects_missing_or_negative_credits(bad_credits):
    app.dependency_overrides[verify_advisor_jwt] = lambda: _override_jwt(staff_id="STAFF-UTM-01", tenant_id="UTM")
    try:
        with patch("app.v1.endpoints.students.SupabaseService") as m1, patch("backend.app.v1.endpoints.students.SupabaseService", create=True) as m2:
            mock_svc, audits = _mock_supabase_for_exemptions(
                student_tenant="UTM",
                assigned_advisor="STAFF-UTM-01",
                caller_staff_id="STAFF-UTM-01",
                caller_tenant="UTM"
            )
            m1.return_value = mock_svc
            m2.return_value = mock_svc

            payload = {"course_actions": [
                {"action": "add", "course_code": "SECJ1013", "grade": "EX", "credits": bad_credits}
            ]}
            resp = client.patch("/api/v1/students/A24MJ5050/exemptions", json=payload)
            assert resp.status_code == 400
            assert "Credits are required" in resp.json()["detail"]
            assert audits == []
    finally:
        app.dependency_overrides.pop(verify_advisor_jwt, None)


def test_missing_credits_raise_instead_of_defaulting(utm_fixture_scale):
    recs = [{"course_code": "SECJ1013", "grade": "A", "credits": None, "semester": "SEM 1 2024/2025"}]
    with pytest.raises(ValueError, match="Missing credits for SECJ1013"):
        compute_cgpa(recs, utm_fixture_scale)
    with pytest.raises(ValueError, match="Missing credits for SECJ1013"):
        compute_completed_credits(recs, utm_fixture_scale)
