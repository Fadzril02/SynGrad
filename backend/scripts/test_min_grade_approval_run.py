"""
Verification Script for Prerequisite Enforcement via /api/v1/audit/finalize-approval

Demonstrates two cases:
Case 1: Unspecified prerequisite (min_grade is None) -> Any passing grade (e.g. 'D') satisfies prerequisite.
Case 2: Explicit min_grade prerequisite (min_grade = 'C') -> Passing with 'D' (GP 1.00 < 2.00) fails with reason.
"""

import os
import sys
import json
from unittest.mock import patch

# Ensure backend package is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def run_case(title: str, catalog: dict, courses: list):
    print("=" * 80)
    print(title)
    print("=" * 80)

    payload = {
        "document_id": "doc-prereq-test-uuid",
        "matric_number": "A24MJ9999",
        "student_name": "Test Candidate",
        "academic_session": "2024/2025",
        "semester": 2,
        "courses": courses
    }

    patch_target = "app.v1.endpoints.audit.supabase_svc" if "app.v1.endpoints.audit" in sys.modules else "backend.app.v1.endpoints.audit.supabase_svc"
    with patch(patch_target) as mock_svc:
        mock_svc.get_template_course_catalog.return_value = catalog
        mock_svc.get_or_create_student.return_value = {"id": "test-student-id", "matric_number": "A24MJ9999"}
        mock_svc.persist_audit_results.return_value = "audit-uuid-test"
        mock_svc.client = None

        response = client.post("/api/v1/audit/finalize-approval", json=payload)
        data = response.json()
        print(f"HTTP Status: {response.status_code}")
        print(f"Overall Traffic Light: {data['summary']['overall_traffic_light']}")
        print(f"Unmet Prerequisites Count: {data['summary']['unmet_prerequisites_count']}")
        for r in data["records"]:
            print(f"  Course: {r['course_code']} | Grade: {r['grade']} | Prereq Met: {r['prerequisite_met']} | Missing: {r['missing_prerequisites']}")

def main():
    # Courses submitted by student
    student_courses = [
        {
            "course_code": "SCSE1013",
            "course_name": "FUNDAMENTAL PROGRAMMING CONCEPTS",
            "grade": "D",
            "credit_hour": 3,
            "credits": 3,
            "status": "Pass",
            "session_semester": "2024/2025-1"
        },
        {
            "course_code": "SCSE2243",
            "course_name": "APPLICATION DEVELOPMENT PROJECT I",
            "grade": "A",
            "credit_hour": 3,
            "credits": 3,
            "status": "Pass",
            "session_semester": "2024/2025-2"
        }
    ]

    # Case 1: Unspecified prerequisite (min_grade is None) -> Any pass satisfies
    catalog_unspecified = {
        "SCSE1013": {"code": "SCSE1013", "name": "Prog I", "credits": 3, "prerequisites": {"courses": []}},
        "SCSE2243": {"code": "SCSE2243", "name": "App Dev Project I", "credits": 3, "prerequisites": {
            "type": "AND", "courses": [{"course_code": "SCSE1013", "min_grade": None}], "min_grade": None
        }}
    }
    run_case("CASE 1: UNSPECIFIED PREREQUISITE (min_grade = None -> 'Any Pass' policy)", catalog_unspecified, student_courses)

    # Case 2: Explicit min_grade prerequisite (min_grade = 'C') -> 'D' pass fails threshold
    catalog_explicit_c = {
        "SCSE1013": {"code": "SCSE1013", "name": "Prog I", "credits": 3, "prerequisites": {"courses": []}},
        "SCSE2243": {"code": "SCSE2243", "name": "App Dev Project I", "credits": 3, "prerequisites": {
            "type": "AND", "courses": [{"course_code": "SCSE1013", "min_grade": "C"}], "min_grade": "C"
        }}
    }
    print()
    run_case("CASE 2: EXPLICIT MIN_GRADE PREREQUISITE (min_grade = 'C' policy)", catalog_explicit_c, student_courses)

if __name__ == "__main__":
    main()
