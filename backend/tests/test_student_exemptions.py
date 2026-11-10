"""PATCH /students/{matric}/exemptions: EX/CT courses must be in the student's degree template."""
import asyncio
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

try:
    from app.v1.endpoints import audit, students
    from app.engine.grading import GradeDefinition, GradingScale
except ImportError:
    from backend.app.v1.endpoints import audit, students
    from backend.app.engine.grading import GradeDefinition, GradingScale


def _svc(catalog, audit_error=None, records=(), syllabus_year="2024/2025"):
    rows = {
        "students": [{"matric_no": "A1", "tenant_id": "UTM", "advisor_staff_id": "S1", "cohort_id": "c1"}],
        "advisors": [{"staff_id": "S1", "tenant_id": "UTM"}],
        "academic_records": list(records),
    }
    client = MagicMock()
    client.queries = []

    def table(name):
        q = MagicMock()
        for m in ("select", "eq", "in_", "limit", "upsert", "delete", "update", "insert"):
            getattr(q, m).return_value = q
        q.execute.return_value = MagicMock(data=rows.get(name, []))
        if name == "exemption_audit" and audit_error:
            q.execute.side_effect = audit_error
        client.queries.append((name, q))
        return q

    client.table.side_effect = table
    svc = MagicMock(client=client)
    svc.get_template_course_catalog.return_value = catalog
    svc.get_student_template.return_value = None if catalog is None else ("t1", syllabus_year)
    return svc


def _patch(svc, code, *more, action="add"):
    req = students.StudentExemptionsPatchRequest(
        course_actions=[{"action": action, "course_code": code, "grade": "EX", "credits": 3}, *more]
    )
    with patch.object(students, "SupabaseService", return_value=svc):
        return asyncio.run(students.patch_student_exemptions("a1", req, {"sub": "u1"}))


def test_course_in_template_is_accepted():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}})
    assert _patch(svc, "SECJ 1013").success
    svc.get_template_course_catalog.assert_called_once_with("A1", "UTM")


def test_course_not_in_template_is_rejected_before_any_write():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}})
    with pytest.raises(HTTPException) as e:
        _patch(svc, "XXXX9999")
    assert e.value.status_code == 400
    assert e.value.detail == "Course XXXX9999 is not in this student's degree template"
    assert _writes(svc) == []


def test_no_template_is_rejected():
    with pytest.raises(HTTPException) as e:
        _patch(_svc(None), "SECJ1013")
    assert e.value.status_code == 400


def test_template_db_error_raises():
    svc = _svc({})
    svc.get_template_course_catalog.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError, match="db down"):
        _patch(svc, "SECJ1013")


def _writes(svc):
    return [n for n, q in svc.client.queries if q.upsert.called or q.delete.called or q.update.called or q.insert.called]


def test_remove_outside_template_is_allowed():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}}, records=[{"course_code": "XXXX9999", "grade": "EX"}])
    assert _patch(svc, "XXXX9999", action="remove").success
    svc.get_template_course_catalog.assert_not_called()
    assert "academic_records" in _writes(svc)


def test_all_items_validated_before_any_write():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}})
    with pytest.raises(HTTPException) as e:
        _patch(svc, "SECJ1013", {"action": "add", "course_code": "SECJ1013", "grade": "A", "credits": 3})
    assert e.value.status_code == 400
    assert _writes(svc) == []


def test_audit_insert_failure_raises():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}}, audit_error=RuntimeError("audit down"))
    with pytest.raises(RuntimeError, match="audit down"):
        _patch(svc, "SECJ1013")


def test_student_lookup_scoped_to_advisor_tenant():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}})
    _patch(svc, "SECJ1013")
    student_q = next(q for n, q in svc.client.queries if n == "students")
    student_q.eq.assert_any_call("tenant_id", "UTM")


def test_remove_only_deletes_exemption_rows():
    svc = _svc({}, records=[{"course_code": "SECJ1013", "grade": "A"}, {"course_code": "SECJ1013", "grade": "EX"}])
    _patch(svc, "SECJ1013", action="remove")
    delete_q = next(q for n, q in svc.client.queries if n == "academic_records" and q.delete.called)
    delete_q.in_.assert_called_once_with("grade", ["EX", "CT"])


@pytest.mark.parametrize("records", [[], [{"course_code": "SECJ1013", "grade": "A"}]])
def test_remove_without_exemption_row_is_404_before_any_write(records):
    svc = _svc({}, records=records)
    with pytest.raises(HTTPException) as e:
        _patch(svc, "SECJ1013", action="remove")
    assert e.value.status_code == 404
    assert _writes(svc) == []


def test_add_rejected_when_course_already_has_real_grade():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}}, records=[{"course_code": "SECJ1013", "grade": "A"}])
    with pytest.raises(HTTPException) as e:
        _patch(svc, "SECJ1013")
    assert e.value.status_code == 400
    assert e.value.detail == "Course SECJ1013 already has a grade; exemption not needed"
    assert _writes(svc) == []


def test_add_rejected_when_course_already_exempted():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}}, records=[{"course_code": "SECJ1013", "grade": "CT"}])
    with pytest.raises(HTTPException) as e:
        _patch(svc, "SECJ1013")
    assert e.value.status_code == 400
    assert e.value.detail == "Course SECJ1013 already exempted — remove it first"
    assert _writes(svc) == []


def test_same_course_twice_is_rejected_before_any_write():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}})
    with pytest.raises(HTTPException) as e:
        _patch(svc, "SECJ1013", {"action": "add", "course_code": "SECJ 1013", "grade": "CT", "credits": 3})
    assert e.value.status_code == 400
    assert _writes(svc) == []


def _inserted_exemption(svc):
    q = next(q for n, q in svc.client.queries if n == "academic_records" and q.insert.called)
    q.upsert.assert_not_called()
    return q.insert.call_args.args[0]


def test_add_stores_real_session_from_template_and_ignores_browser_label():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}}, syllabus_year="2024/25")
    req = students.StudentExemptionsPatchRequest(course_actions=[
        {"action": "add", "course_code": "SECJ1013", "grade": "EX", "credits": 3, "semester": "Sem 3"}
    ])
    with patch.object(students, "SupabaseService", return_value=svc):
        asyncio.run(students.patch_student_exemptions("a1", req, {"sub": "u1"}))
    assert _inserted_exemption(svc)["semester"] == "SEM 1 2024/2025"


def test_bad_syllabus_year_is_rejected_before_any_write():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}}, syllabus_year="2024")
    with pytest.raises(HTTPException) as e:
        _patch(svc, "SECJ1013")
    assert e.value.status_code == 400
    assert "2024" in e.value.detail
    assert _writes(svc) == []


def test_add_exemption_then_approve_slip_works():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}})
    _patch(svc, "SECJ1013")
    saved = _inserted_exemption(svc)

    audit_svc = MagicMock()
    audit_svc.client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[saved])
    audit_svc.get_template_course_catalog.return_value = {}
    audit_svc.get_student_block_exempted_credits.return_value = (0, 130)
    audit_svc.persist_audit_results.return_value = "audit-1"
    scale = GradingScale("UTM", [
        GradeDefinition("A", 4.0, 1, True, True, True),
        GradeDefinition("EX", None, None, True, False, True),
    ])
    request = audit.FinalizeApprovalRequest(
        document_id="doc-1", matric_number="A1", academic_session="2024/2025", semester=2,
        courses=[{"course_code": "SECJ1023", "course_name": "PT2", "grade": "A", "credits": 3, "credit_hour": 3, "status": "Pass"}],
    )
    jwt = {"sub": "u1", "app_metadata": {"staff_id": "S1", "tenant_id": "UTM"}}
    with patch.object(audit, "supabase_svc", audit_svc), patch.object(audit, "load_scale", return_value=scale),             patch.object(audit, "_load_repeat_policy", return_value="latest"),             patch.object(audit, "_extract_advisor_id", return_value="S1"), patch.object(audit, "_extract_tenant_id", return_value="UTM"),             patch.object(audit, "_load_authorized_document"):
        result = asyncio.run(audit.finalize_approval(request, jwt))

    assert result.success
    assert result.summary.total_credits_earned == 6
    persisted = {r.course_code: r.semester for r in audit_svc.persist_audit_results.call_args.kwargs["records"]}
    assert persisted == {"SECJ1013": "SEM 1 2024/2025", "SECJ1023": "SEM 2 2024/2025"}
