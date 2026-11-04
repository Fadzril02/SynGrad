"""get_template_course_catalog / get_student_required_credits: read the student's template; DB errors raise."""
from unittest.mock import MagicMock
import pytest

try:
    from app.core.supabase_client import SupabaseService
except ImportError:
    from backend.app.core.supabase_client import SupabaseService


def _svc(tables):
    """tables: name -> rows list (filtered by .eq on columns the row has), or an Exception raised on execute()."""
    svc = SupabaseService.__new__(SupabaseService)
    svc.init_error = None
    client = MagicMock()

    def table(name):
        q = MagicMock()
        filters = []
        q.select.return_value = q
        q.limit.return_value = q
        q.eq.side_effect = lambda col, val: (filters.append((col, val)), q)[1]
        result = tables[name]
        if isinstance(result, Exception):
            q.execute.side_effect = result
        else:
            q.execute.side_effect = lambda: MagicMock(
                data=[r for r in result if all(r.get(c, v) == v for c, v in filters)]
            )
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
    cat = svc.get_template_course_catalog("a24mj0001", "UTM")
    assert cat["SECJ1023"]["prerequisites"]["courses"] == ["SECJ1013"]
    assert cat["SECJ1023"]["credits"] == 3


def test_no_cohort_returns_none():
    svc = _svc({"students": [{"cohort_id": None}]})
    assert svc.get_template_course_catalog("A1", "UTM") is None


def test_db_error_raises():
    svc = _svc({"students": [{"cohort_id": "c1"}], "cohorts": RuntimeError("db down")})
    with pytest.raises(RuntimeError, match="db down"):
        svc.get_template_course_catalog("A1", "UTM")


def test_required_credits_from_template():
    svc = _svc({
        "students": [{"cohort_id": "c1"}],
        "cohorts": [{"template_id": "t1"}],
        "degree_templates": [{"total_credits_required": 130}],
    })
    assert svc.get_student_required_credits("a24mj0001", "UTM") == 130


def test_required_credits_no_template_returns_none():
    svc = _svc({"students": [{"cohort_id": "c1"}], "cohorts": [{"template_id": None}]})
    assert svc.get_student_required_credits("A1", "UTM") is None


def test_required_credits_db_error_raises():
    svc = _svc({"students": RuntimeError("db down")})
    with pytest.raises(RuntimeError, match="db down"):
        svc.get_student_required_credits("A1", "UTM")


def test_template_lookup_scoped_to_tenant():
    svc = _svc({
        "students": [
            {"tenant_id": "UTM", "matric_no": "A1", "cohort_id": "c-utm"},
            {"tenant_id": "UNIKL", "matric_no": "A1", "cohort_id": "c-unikl"},
        ],
        "cohorts": [{"id": "c-utm", "template_id": "t-utm"}, {"id": "c-unikl", "template_id": "t-unikl"}],
    })
    assert svc._student_template_id("a1", "UNIKL") == "t-unikl"
    assert svc._student_template_id("a1", "UTM") == "t-utm"


def test_template_lookup_requires_tenant():
    with pytest.raises(ValueError):
        _svc({})._student_template_id("A1", "")
