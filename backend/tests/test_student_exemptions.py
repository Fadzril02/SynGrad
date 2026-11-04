"""PATCH /students/{matric}/exemptions: EX/CT courses must be in the student's degree template."""
import asyncio
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

try:
    from app.v1.endpoints import students
except ImportError:
    from backend.app.v1.endpoints import students


def _svc(catalog, audit_error=None, records=()):
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
    assert "academic_records" not in [c.args[0] for c in svc.client.table.call_args_list]


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
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}})
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
    svc = _svc({}, records=[{"id": "r1", "grade": "A"}])
    _patch(svc, "SECJ1013", action="remove")
    delete_q = next(q for n, q in svc.client.queries if n == "academic_records" and q.delete.called)
    delete_q.in_.assert_called_once_with("grade", ["EX", "CT"])


def test_add_rejected_when_course_already_has_real_grade():
    svc = _svc({"SECJ1013": {"code": "SECJ1013"}}, records=[{"course_code": "SECJ1013", "grade": "A"}])
    with pytest.raises(HTTPException) as e:
        _patch(svc, "SECJ1013")
    assert e.value.status_code == 400
    assert e.value.detail == "Course SECJ1013 already has a grade; exemption not needed"
    assert _writes(svc) == []
