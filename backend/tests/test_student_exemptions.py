"""PATCH /students/{matric}/exemptions: EX/CT courses must be in the student's degree template."""
import asyncio
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

try:
    from app.v1.endpoints import students
except ImportError:
    from backend.app.v1.endpoints import students


def _svc(catalog):
    rows = {
        "students": [{"matric_no": "A1", "tenant_id": "UTM", "advisor_staff_id": "S1", "cohort_id": "c1"}],
        "advisors": [{"staff_id": "S1", "tenant_id": "UTM"}],
    }
    client = MagicMock()

    def table(name):
        q = MagicMock()
        for m in ("select", "eq", "limit", "upsert", "delete", "update", "insert"):
            getattr(q, m).return_value = q
        q.execute.return_value = MagicMock(data=rows.get(name, []))
        return q

    client.table.side_effect = table
    svc = MagicMock(client=client)
    svc.get_template_course_catalog.return_value = catalog
    return svc


def _patch(svc, code):
    req = students.StudentExemptionsPatchRequest(
        course_actions=[{"action": "add", "course_code": code, "grade": "EX", "credits": 3}]
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
