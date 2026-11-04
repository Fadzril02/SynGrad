"""get_template_course_catalog / get_student_required_credits: read the student's template; DB errors raise."""
from unittest.mock import MagicMock
import pytest

try:
    from app.core.supabase_client import SupabaseService
except ImportError:
    from backend.app.core.supabase_client import SupabaseService


def _svc(tables):
    """tables: name -> rows list, or an Exception to raise on execute()."""
    svc = SupabaseService.__new__(SupabaseService)
    svc.init_error = None
    client = MagicMock()

    def table(name):
        q = MagicMock()
        q.select.return_value = q
        q.eq.return_value = q
        q.limit.return_value = q
        result = tables[name]
        if isinstance(result, Exception):
            q.execute.side_effect = result
        else:
            q.execute.return_value = MagicMock(data=result)
        return q

    client.table.side_effect = table
    svc.client = client
    return svc


def test_maps_template_courses_by_code():
    svc = _svc({
        "students": [{"cohort_id": "c1"}],
        "cohorts": [{"template_id": "t1"}],
        "template_courses": [{
            "course_code": "SECJ 1023", "course_name": "Prog II", "credit_hour": 3,
            "category": "Core", "prerequisites": {"type": "AND", "courses": ["SECJ1013"]},
        }],
    })
    cat = svc.get_template_course_catalog("a24mj0001")
    assert cat["SECJ1023"]["prerequisites"]["courses"] == ["SECJ1013"]
    assert cat["SECJ1023"]["credits"] == 3


def test_no_cohort_returns_none():
    svc = _svc({"students": [{"cohort_id": None}]})
    assert svc.get_template_course_catalog("A1") is None


def test_db_error_raises():
    svc = _svc({"cohorts": RuntimeError("db down")})
    with pytest.raises(RuntimeError, match="db down"):
        svc.get_template_course_catalog("A1", cohort_id="c1")


def test_required_credits_from_template():
    svc = _svc({
        "students": [{"cohort_id": "c1"}],
        "cohorts": [{"template_id": "t1"}],
        "degree_templates": [{"total_credits_required": 130}],
    })
    assert svc.get_student_required_credits("a24mj0001") == 130


def test_required_credits_no_template_returns_none():
    svc = _svc({"students": [{"cohort_id": "c1"}], "cohorts": [{"template_id": None}]})
    assert svc.get_student_required_credits("A1") is None


def test_required_credits_db_error_raises():
    svc = _svc({"students": RuntimeError("db down")})
    with pytest.raises(RuntimeError, match="db down"):
        svc.get_student_required_credits("A1")
