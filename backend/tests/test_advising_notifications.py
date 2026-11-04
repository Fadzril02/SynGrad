import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.auth import verify_advisor_jwt
except ImportError:
    from backend.app.main import app
    from backend.app.core.auth import verify_advisor_jwt

client = TestClient(app)

def override_advisor_jwt():
    return {
        "sub": "advisor-uuid-123",
        "email": "advisor@university.edu.my",
        "app_metadata": {"staff_id": "STAFF-001"}
    }

@pytest.fixture(autouse=True)
def setup_jwt_override():
    app.dependency_overrides[verify_advisor_jwt] = override_advisor_jwt
    yield
    app.dependency_overrides.pop(verify_advisor_jwt, None)


def _setup_mock_supabase(mock_supa_cls, log_data, recent_notifs=None, student_data=None, advisor_data=None):
    mock_svc = MagicMock()
    mock_supa_cls.return_value = mock_svc
    mock_client = MagicMock()
    mock_svc.client = mock_client

    # Table mocks
    def mock_table(table_name):
        tbl = MagicMock()
        if table_name == "advising_logs":
            # For select
            select_mock = MagicMock()
            tbl.select.return_value = select_mock
            
            # log fetch: .select("*").eq("id", log_id).limit(1).execute()
            eq_mock = MagicMock()
            select_mock.eq.return_value = eq_mock
            eq_mock.limit.return_value.execute.return_value = MagicMock(data=[log_data] if log_data else [])
            eq_mock.eq.return_value = eq_mock  # extra tenant_id filter
            
            # rate limit check: .select("id, notified_at").eq("student_matric_no", ...).neq("id", ...).gte("notified_at", ...).limit(1).execute()
            neq_mock = MagicMock()
            eq_mock.neq.return_value = neq_mock
            gte_mock = MagicMock()
            neq_mock.gte.return_value = gte_mock
            gte_mock.limit.return_value.execute.return_value = MagicMock(data=recent_notifs or [])
            
            # update: tbl.update({"notified_at": ...}).eq("id", log_id).execute()
            update_mock = MagicMock()
            tbl.update.return_value = update_mock
            update_mock.eq.return_value.execute.return_value = MagicMock(data=[{"id": log_data.get("id")} if log_data else {}])

        elif table_name == "students":
            select_mock = MagicMock()
            tbl.select.return_value = select_mock
            eq_mock = MagicMock()
            select_mock.eq.return_value = eq_mock
            st_data = student_data if student_data is not None else {"name": "Test Student", "institutional_email": "student@university.edu.my"}
            eq_mock.limit.return_value.execute.return_value = MagicMock(data=[st_data] if st_data else [])
            eq_mock.eq.return_value = eq_mock  # extra tenant_id filter

        elif table_name == "advisors":
            select_mock = MagicMock()
            tbl.select.return_value = select_mock
            eq_mock = MagicMock()
            select_mock.eq.return_value = eq_mock
            if advisor_data is None:
                adv_list = [{"name": "Dr. Advisor", "staff_id": "STAFF-001"}]
            elif isinstance(advisor_data, list):
                adv_list = advisor_data
            else:
                adv_list = [advisor_data]
            eq_mock.limit.return_value.execute.return_value = MagicMock(data=adv_list)
            eq_mock.execute.return_value = MagicMock(data=adv_list)
            eq_mock.or_.return_value.execute.return_value = MagicMock(data=adv_list)

        return tbl

    mock_client.table.side_effect = mock_table
    return mock_svc


# 1. Owner check: 403 unless log.advisor_staff_id belongs to JWT user
@patch("backend.app.v1.endpoints.advising.SupabaseService")
def test_notify_owner_check_fails(mock_supa):
    log_data = {
        "id": "log-001",
        "student_matric_no": "A24CS0001",
        "advisor_staff_id": "STAFF-999",  # Different from token's STAFF-001
        "visibility": "shared",
        "notified_at": None,
    }
    _setup_mock_supabase(mock_supa, log_data, advisor_data=[])

    resp = client.post("/api/v1/advising-logs/log-001/notify", headers={"Authorization": "Bearer mock"})
    assert resp.status_code == 403
    assert "Forbidden" in resp.json()["detail"]


# 2. Private note: 400 if visibility != 'shared'
@patch("backend.app.v1.endpoints.advising.SupabaseService")
def test_notify_private_note_fails(mock_supa):
    log_data = {
        "id": "log-002",
        "student_matric_no": "A24CS0001",
        "advisor_staff_id": "STAFF-001",
        "visibility": "private",  # Private
        "notified_at": None,
    }
    _setup_mock_supabase(mock_supa, log_data)

    resp = client.post("/api/v1/advising-logs/log-002/notify", headers={"Authorization": "Bearer mock"})
    assert resp.status_code == 400
    assert "not 'shared'" in resp.json()["detail"]


# 3. Already notified: 409 if notified_at is not null
@patch("backend.app.v1.endpoints.advising.SupabaseService")
def test_notify_already_notified_fails(mock_supa):
    log_data = {
        "id": "log-003",
        "student_matric_no": "A24CS0001",
        "advisor_staff_id": "STAFF-001",
        "visibility": "shared",
        "notified_at": "2026-09-30T10:00:00Z",
    }
    _setup_mock_supabase(mock_supa, log_data)

    resp = client.post("/api/v1/advising-logs/log-003/notify", headers={"Authorization": "Bearer mock"})
    assert resp.status_code == 409
    assert "already been notified" in resp.json()["detail"]


# 4. Rate limit: skip (return {sent:false, reason:"rate_limited"})
@patch("backend.app.v1.endpoints.advising.SupabaseService")
def test_notify_rate_limited(mock_supa):
    log_data = {
        "id": "log-004",
        "student_matric_no": "A24CS0001",
        "advisor_staff_id": "STAFF-001",
        "visibility": "shared",
        "notified_at": None,
    }
    # Student had a notification 10 minutes ago
    recent_notifs = [{"id": "log-earlier", "notified_at": "2026-09-30T22:00:00Z"}]
    _setup_mock_supabase(mock_supa, log_data, recent_notifs=recent_notifs)

    resp = client.post("/api/v1/advising-logs/log-004/notify", headers={"Authorization": "Bearer mock"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is False
    assert body["reason"] == "rate_limited"


# 5. Missing env: 500 fail loud if RESEND_API_KEY or RESEND_FROM is missing
@patch("backend.app.v1.endpoints.advising.SupabaseService")
def test_notify_missing_env_fails(mock_supa, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM", raising=False)

    log_data = {
        "id": "log-005",
        "student_matric_no": "A24CS0001",
        "advisor_staff_id": "STAFF-001",
        "visibility": "shared",
        "notified_at": None,
    }
    _setup_mock_supabase(mock_supa, log_data)

    resp = client.post("/api/v1/advising-logs/log-005/notify", headers={"Authorization": "Bearer mock"})
    assert resp.status_code == 500
    assert "Missing RESEND_API_KEY" in resp.json()["detail"]


# 6. Success: sends via Resend, sets notified_at, returns {sent: true}
@patch("backend.app.v1.endpoints.advising.SupabaseService")
@patch("httpx.AsyncClient.post")
def test_notify_success(mock_post, mock_supa, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_123456789")
    monkeypatch.setenv("RESEND_FROM", "SynGrad <no-reply@syngrad.my>")

    # Mock successful Resend response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "email_123"}
    mock_post.return_value = mock_resp

    log_data = {
        "id": "log-006",
        "student_matric_no": "A24CS0001",
        "advisor_staff_id": "STAFF-001",
        "visibility": "shared",
        "notified_at": None,
        "notes": "Secret student confidential notes that must not leak",
        "action_item": "Secret action item",
    }
    student_data = {
        "name": "Jane Doe",
        "institutional_email": "jane.doe@university.edu.my",
    }
    advisor_data = {
        "name": "Dr. John Smith",
        "staff_id": "STAFF-001",
    }
    _setup_mock_supabase(mock_supa, log_data, student_data=student_data, advisor_data=advisor_data)

    resp = client.post("/api/v1/advising-logs/log-006/notify", headers={"Authorization": "Bearer mock"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is True
    assert body["notified_at"] is not None

    # Verify Resend API call details
    assert mock_post.called
    call_kwargs = mock_post.call_args.kwargs
    payload = call_kwargs["json"]
    assert payload["from"] == "SynGrad <no-reply@syngrad.my>"
    assert payload["to"] == ["jane.doe@university.edu.my"]
    assert "Dr. John Smith" in payload["text"]
    assert "Jane Doe" in payload["text"]
    assert "https://syngrad.my" in payload["text"]
    # PDPA check: must NOT leak notes or action items in email body
    assert "Secret student confidential notes" not in payload["text"]
    assert "Secret action item" not in payload["text"]
