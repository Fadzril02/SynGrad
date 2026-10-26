"""
Integration and End-to-End Tests for Finalize Approval Endpoint
Validates that approving staged transcript data:
1. Passes through DAG graph resolver with prerequisite min-grade checks
2. Persists validated results into 'academic_records' and 'degree_audits'
3. Updates 'uploaded_documents.processing_status' to 'Approved'
4. Enforces strict advisor_id requirement (throws 400 if missing)
"""

import sys
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

try:
    from app.main import app
    from app.schemas.audit import FinalizeApprovalRequest, ExtractedCourseItem
    from app.core.auth import verify_advisor_jwt
except ImportError:
    from backend.app.main import app
    from backend.app.schemas.audit import FinalizeApprovalRequest, ExtractedCourseItem
    from backend.app.core.auth import verify_advisor_jwt

client = TestClient(app)

# Override JWT verification for test client
app.dependency_overrides[verify_advisor_jwt] = lambda: {
    "email": "advisor@university.edu.my",
    "sub": "mock-advisor-uid",
    "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"}
}

AUTH_HEADERS = {"Authorization": "Bearer mock-test-token"}

try:
    from app.engine.grading import GradingScale, GradeDefinition
except ImportError:
    from backend.app.engine.grading import GradingScale, GradeDefinition


@pytest.fixture(autouse=True)
def mock_load_scale_fixture():
    test_scale = GradingScale("TEST_FIXTURE_TENANT", [
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
        GradeDefinition("CT", None, None, True, False, True),
    ])
    patch_target = "app.v1.endpoints.audit.load_scale" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.load_scale"
    with patch(patch_target, return_value=test_scale):
        yield


def test_finalize_approval_fastapi_endpoint_flow():
    """Test that finalize-approval endpoint audits courses, sets traffic light, and creates records."""
    mock_supabase = MagicMock()
    
    # Mock course catalog with prerequisite
    mock_catalog = {
        "SECJ1013": {"course_code": "SECJ1013", "prerequisites": {"type": "AND", "courses": []}},
        "SECJ1023": {
            "course_code": "SECJ1023",
            "prerequisites": {
                "type": "AND",
                "courses": [{"course_code": "SECJ1013", "min_grade": "C"}]
            }
        },
        "SECJ2013": {
            "course_code": "SECJ2013",
            "prerequisites": {
                "type": "AND",
                "courses": [{"course_code": "SECJ1023", "min_grade": "C"}]
            }
        }
    }
    
    mock_student = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "matric_number": "TEST-SE24-FINAL",
        "student_name": "Test Finalize Student"
    }

    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "TEST-SE24-FINAL",
        "student_name": "Test Finalize Student",
        "advisor_id": "STAFF-001",
        "academic_session": "2024/2025",
        "semester": 1,
        "courses": [
            {
                "course_code": "SECJ1013",
                "course_name": "Programming Technique I",
                "grade": "A",
                "credit_hour": 3,
                "credits": 3,
                "status": "Pass",
                "session_semester": "2024/2025-1"
            },
            {
                "course_code": "SECJ1023",
                "course_name": "Programming Technique II",
                "grade": "B+",
                "credit_hour": 3,
                "credits": 3,
                "status": "Pass",
                "session_semester": "2024/2025-2"
            }
        ]
    }

    patch_target = "app.v1.endpoints.audit.supabase_svc" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.supabase_svc"
    patch_id_target = "app.v1.endpoints.audit._check_advisor_identity" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit._check_advisor_identity"
    
    with patch(patch_target) as mock_svc, patch(patch_id_target) as mock_check_id:
        mock_svc.get_university_course_catalog.return_value = mock_catalog
        mock_svc.get_or_create_student.return_value = mock_student
        mock_svc.persist_audit_results.return_value = "audit-uuid-12345"
        mock_svc.get_student_block_exempted_credits.return_value = (0, None)
        mock_svc.client = mock_supabase

        response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["audit_id"] == "audit-uuid-12345"
        assert data["processing_status"] == "Approved"
        assert data["records_saved_count"] == 2
        assert data["summary"]["overall_traffic_light"] == "GREEN"
        assert data["records"][0]["traffic_light"] == "GREEN"
        assert data["records"][1]["traffic_light"] == "GREEN"

        # Verify persist_audit_results was called directly with matric_no string
        mock_svc.persist_audit_results.assert_called_once()
        call_args = mock_svc.persist_audit_results.call_args[1]
        assert (call_args.get("matric_no") or call_args.get("student_id")) == "TEST-SE24-FINAL"
        records = call_args["records"]
        assert len(records) == 2
        assert records[0].course_code == "SECJ1013"
        assert records[0].prerequisite_met is True
        assert records[1].course_code == "SECJ1023"
        assert records[1].prerequisite_met is True

        # Verify uploaded_documents was updated to 'Approved'
        mock_supabase.table.assert_called_with("uploaded_documents")
        mock_supabase.table().update.assert_called_with({"processing_status": "Approved"})


def test_finalize_approval_missing_jwt_advisor_id_403():
    """Test that a JWT lacking advisor identity returns 403 Forbidden."""
    # Temporarily override JWT dependency to return a payload without staff_id in app_metadata or DB
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "email": "advisor@university.edu.my",
        "sub": "mock-advisor-uid",
        "app_metadata": {"tenant_id": "UTM"}
    }
    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "TEST-SE24-FINAL",
        "courses": [
            {
                "course_code": "SECJ1013",
                "grade": "A"
            }
        ]
    }
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().limit().execute.return_value.data = []
    patch_target = "app.v1.endpoints.audit.supabase_svc" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.supabase_svc"
    try:
        with patch(patch_target) as mock_svc:
            mock_svc.client = mock_supabase
            response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
            assert response.status_code == 403
            assert "Advisor identity cannot be securely verified" in response.json()["detail"]
    finally:
        # Restore mock advisor JWT
        app.dependency_overrides[verify_advisor_jwt] = lambda: {
            "email": "advisor@university.edu.my",
            "sub": "mock-advisor-uid",
            "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"}
        }


def test_finalize_approval_empty_courses_error():
    """Test validation error when no courses are submitted."""
    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "TEST-SE24-EMPTY",
        "advisor_id": "STAFF-001",
        "courses": []
    }
    patch_id_target = "app.v1.endpoints.audit._check_advisor_identity" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit._check_advisor_identity"
    with patch(patch_id_target):
        response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 400
    assert "No course records provided" in response.json()["detail"]


def test_finalize_approval_missing_matric_422():
    """Test validation error (422) when matric_number is missing or empty."""
    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "   ",
        "advisor_id": "STAFF-001",
        "courses": [
            {
                "course_code": "SECJ1013",
                "grade": "A"
            }
        ]
    }
    patch_id_target = "app.v1.endpoints.audit._check_advisor_identity" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit._check_advisor_identity"
    with patch(patch_id_target):
        response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422
    assert "matric_number is required" in response.json()["detail"]


def test_finalize_approval_forged_tenant_idor_ignored():
    """
    Strict regression test for IDOR vulnerability:
    Mock a JWT with app_metadata: {"tenant_id": "SECURE_UM"}, but send a request body
    containing tenant_id: "HACKED_UTM". Assert that the endpoint processes the request
    under "SECURE_UM", completely ignoring the malicious body.
    """
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "email": "advisor@um.edu.my",
        "sub": "mock-advisor-uid",
        "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "SECURE_UM"}
    }
    mock_supabase = MagicMock()
    mock_catalog = {
        "SECJ1013": {"course_code": "SECJ1013", "prerequisites": {"type": "AND", "courses": []}}
    }
    mock_student = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "matric_number": "TEST-SE24-IDOR",
        "student_name": "Test IDOR Student"
    }
    # Attacker passes spoofed tenant_id="HACKED_UTM" in request body
    payload = {
        "tenant_id": "HACKED_UTM",
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "TEST-SE24-IDOR",
        "student_name": "Test IDOR Student",
        "advisor_id": "STAFF-001",
        "academic_session": "2024/2025",
        "semester": 1,
        "courses": [{"course_code": "SECJ1013", "grade": "A", "credit_hour": 3}]
    }

    patch_target = "app.v1.endpoints.audit.supabase_svc" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.supabase_svc"
    try:
        with patch(patch_target) as mock_svc:
            mock_svc.get_university_course_catalog.return_value = mock_catalog
            mock_svc.get_or_create_student.return_value = mock_student
            mock_svc.persist_audit_results.return_value = "audit-uuid-idor"
            mock_svc.get_student_block_exempted_credits.return_value = (0, None)
            mock_svc.client = mock_supabase

            response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
            assert response.status_code == 200
            
            # Assert persist_audit_results was called with 'SECURE_UM', NOT 'HACKED_UTM'
            mock_svc.persist_audit_results.assert_called_once()
            call_kwargs = mock_svc.persist_audit_results.call_args[1]
            assert call_kwargs["tenant_id"] == "SECURE_UM"
            assert call_kwargs["tenant_id"] != "HACKED_UTM"
    finally:
        app.dependency_overrides[verify_advisor_jwt] = lambda: {
            "email": "advisor@university.edu.my",
            "sub": "mock-advisor-uid",
            "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"}
        }


def test_finalize_approval_unverifiable_tenant_raises_403():
    """Verify that if tenant cannot be securely verified, endpoint raises 403 Forbidden."""
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "email": "advisor@unknown.edu.my",
        "sub": "mock-advisor-uid",
        "app_metadata": {"staff_id": "STAFF-001"}  # Missing tenant_id/university_id
    }
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().limit().execute.return_value.data = []

    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "TEST-SE24-403",
        "advisor_id": "STAFF-001",
        "courses": [{"course_code": "SECJ1013", "grade": "A", "credit_hour": 3}]
    }

    patch_target = "app.v1.endpoints.audit.supabase_svc" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.supabase_svc"
    try:
        with patch(patch_target) as mock_svc:
            mock_svc.client = mock_supabase
            response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
            assert response.status_code == 403
            assert "Tenant ID cannot be securely verified" in response.json()["detail"]
    finally:
        app.dependency_overrides[verify_advisor_jwt] = lambda: {
            "email": "advisor@university.edu.my",
            "sub": "mock-advisor-uid",
            "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"}
        }


def test_finalize_approval_resolves_seeded_utm_uuid():
    """Verify that a seeded UTM UUID ('00000000-0000-0000-0000-000000000001') in university_id resolves to 'UTM'."""
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "email": "advisor@utm.edu.my",
        "sub": "mock-advisor-uid",
        "app_metadata": {"staff_id": "STAFF-001", "university_id": "00000000-0000-0000-0000-000000000001"}
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
        "courses": [{"course_code": "SECJ1013", "grade": "A", "credit_hour": 3}]
    }

    patch_target = "app.v1.endpoints.audit.supabase_svc" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.supabase_svc"
    try:
        with patch(patch_target) as mock_svc:
            mock_svc.get_university_course_catalog.return_value = mock_catalog
            mock_svc.get_or_create_student.return_value = mock_student
            mock_svc.persist_audit_results.return_value = "audit-uuid-test"
            mock_svc.get_student_block_exempted_credits.return_value = (0, None)
            mock_svc.client = mock_supabase

            response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
            assert response.status_code == 200

            mock_svc.persist_audit_results.assert_called_once()
            call_kwargs = mock_svc.persist_audit_results.call_args[1]
            assert call_kwargs["tenant_id"] == "UTM"
    finally:
        app.dependency_overrides[verify_advisor_jwt] = lambda: {
            "email": "advisor@university.edu.my",
            "sub": "mock-advisor-uid",
            "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"}
        }


def test_finalize_approval_resolves_custom_university_uuid_from_db():
    """Verify that a custom university UUID resolves to its institution code string via universities table."""
    custom_uuid = "22222222-2222-2222-2222-222222222222"
    app.dependency_overrides[verify_advisor_jwt] = lambda: {
        "email": "advisor@usm.edu.my",
        "sub": "mock-advisor-uid",
        "app_metadata": {"staff_id": "STAFF-001", "university_id": custom_uuid}
    }
    mock_supabase = MagicMock()
    # Mock universities table query returning code 'USM'
    mock_supabase.table().select().eq().limit().execute.return_value.data = [{"code": "USM", "repeat_policy": "latest"}]

    mock_catalog = {
        "SECJ1013": {"course_code": "SECJ1013", "prerequisites": {"type": "AND", "courses": []}}
    }
    mock_student = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "matric_number": "A24CS0002",
        "student_name": "Test USM Student"
    }
    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "A24CS0002",
        "advisor_id": "STAFF-001",
        "academic_session": "2024/2025",
        "semester": 1,
        "courses": [{"course_code": "SECJ1013", "grade": "A", "credit_hour": 3}]
    }

    patch_target = "app.v1.endpoints.audit.supabase_svc" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.supabase_svc"
    try:
        with patch(patch_target) as mock_svc:
            mock_svc.get_university_course_catalog.return_value = mock_catalog
            mock_svc.get_or_create_student.return_value = mock_student
            mock_svc.persist_audit_results.return_value = "audit-uuid-usm"
            mock_svc.get_student_block_exempted_credits.return_value = (0, None)
            mock_svc.client = mock_supabase

            response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)
            assert response.status_code == 200

            mock_svc.persist_audit_results.assert_called_once()
            call_kwargs = mock_svc.persist_audit_results.call_args[1]
            assert call_kwargs["tenant_id"] == "USM"
    finally:
        app.dependency_overrides[verify_advisor_jwt] = lambda: {
            "email": "advisor@university.edu.my",
            "sub": "mock-advisor-uid",
            "app_metadata": {"staff_id": "STAFF-001", "tenant_id": "UTM"}
        }


def test_extract_tenant_id_queries_advisors_tenant_id():
    """Verify _extract_tenant_id queries public.advisors.tenant_id by user_id."""
    try:
        from app.v1.endpoints.audit import _extract_tenant_id, supabase_svc
    except ImportError:
        from backend.app.v1.endpoints.audit import _extract_tenant_id, supabase_svc

    mock_client = MagicMock()
    mock_client.table().select().eq().limit().execute.return_value.data = [{"tenant_id": "UTM"}]

    with patch.object(supabase_svc, "client", mock_client):
        tenant = _extract_tenant_id({"sub": "advisor-user-123"})
        assert tenant == "UTM"
        mock_client.table.assert_called_with("advisors")
        mock_client.table().select.assert_called_with("tenant_id")
        mock_client.table().select().eq.assert_called_with("user_id", "advisor-user-123")


def test_extract_advisor_id_queries_advisors_staff_id():
    """Verify _extract_advisor_id queries public.advisors.staff_id by user_id and returns staff_id string."""
    try:
        from app.v1.endpoints.audit import _extract_advisor_id, supabase_svc
    except ImportError:
        from backend.app.v1.endpoints.audit import _extract_advisor_id, supabase_svc

    mock_client = MagicMock()
    mock_client.table().select().eq().limit().execute.return_value.data = [{"staff_id": "TEST123"}]

    with patch.object(supabase_svc, "client", mock_client):
        staff_id = _extract_advisor_id({"sub": "advisor-user-456"})
        assert staff_id == "TEST123"
        mock_client.table.assert_called_with("advisors")
        mock_client.table().select.assert_called_with("staff_id")
        mock_client.table().select().eq.assert_called_with("user_id", "advisor-user-456")




@pytest.mark.parametrize("bad_course", [
    {"course_code": "SECJ1023", "grade": "B+"},                                       # missing
    {"course_code": "SECJ1023", "grade": "B+", "credits": None, "credit_hour": None},  # explicit null
    {"course_code": "SECJ1023", "grade": "B+", "credits": 0},                         # zero
    {"course_code": "SECJ1023", "grade": "B+", "credits": 1.5},                       # decimal
    {"course_code": "SECJ1023", "grade": "B+", "credits": "abc"},                     # garbage
])
def test_finalize_approval_bad_credits_422_saves_nothing(bad_course):
    """No `or 3` fallback: one bad row rejects the whole approval and nothing is written."""
    payload = {
        "document_id": "99999999-9999-9999-9999-999999999999",
        "matric_number": "TEST-SE24-FINAL",
        "academic_session": "2024/2025",
        "semester": 1,
        "courses": [
            {"course_code": "SECJ1013", "grade": "A", "credits": 3},
            bad_course,
            {"course_code": "SECJ2013", "grade": "A"},
        ],
    }
    patch_target = "app.v1.endpoints.audit.supabase_svc" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.supabase_svc"
    patch_id_target = "app.v1.endpoints.audit._check_advisor_identity" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit._check_advisor_identity"

    with patch(patch_target) as mock_svc, patch(patch_id_target):
        mock_svc.client = MagicMock()
        response = client.post("/api/v1/audit/finalize-approval", json=payload, headers=AUTH_HEADERS)

        assert response.status_code == 422
        assert response.json()["detail"] == "Credits missing for: SECJ1023, SECJ2013 — please fix and resubmit"
        mock_svc.persist_audit_results.assert_not_called()
        mock_svc.get_or_create_student.assert_not_called()
        mock_svc.delete_file_from_storage.assert_not_called()
        mock_svc.client.table.return_value.update.assert_not_called()


def test_finalize_approval_credit_hour_used_when_credits_absent():
    try:
        from app.v1.endpoints.audit import _parse_credits
    except ImportError:
        from backend.app.v1.endpoints.audit import _parse_credits
    assert _parse_credits(ExtractedCourseItem(course_code="X", grade="A", credit_hour=4)) == 4
    assert _parse_credits(ExtractedCourseItem(course_code="X", grade="A", credits="3", credit_hour=4)) == 3
    assert _parse_credits(ExtractedCourseItem(course_code="X", grade="A", credits=3.0)) == 3
    assert _parse_credits(ExtractedCourseItem(course_code="X", grade="A")) is None
