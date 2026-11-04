"""get_template_course_catalog: reads the student's template_courses; DB errors raise."""
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
