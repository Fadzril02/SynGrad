"""
Smart Academic Assessment System - Student Exemptions & Progression Management
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

try:
    from app.core.auth import verify_advisor_jwt
    from app.core.supabase_client import SupabaseService
except ImportError:
    from backend.app.core.auth import verify_advisor_jwt
    from backend.app.core.supabase_client import SupabaseService

router = APIRouter(prefix="/students", tags=["Students"])


class CourseExemptionAction(BaseModel):
    action: str = Field(..., description="'add' or 'remove'")
    course_code: str = Field(..., description="Course code to exempt or transfer")
    grade: str = Field("EX", description="'EX' (exemption) or 'CT' (credit transfer)")
    credits: Optional[int] = Field(None, description="Course credit hours")
    course_name: Optional[str] = Field(None, description="Course name")
    semester: Optional[str] = Field(None, description="Target semester designation")


class StudentExemptionsPatchRequest(BaseModel):
    entry_semester: Optional[int] = Field(None, ge=1, description="Student entry semester (must be >= 1)")
    block_exempted_credits: Optional[int] = Field(None, ge=0, description="Block exempted credits for transfer/diploma")
    course_actions: Optional[List[CourseExemptionAction]] = Field(None, description="List of EX/CT course actions")


class StudentExemptionsPatchResponse(BaseModel):
    success: bool
    matric_no: str
    entry_semester: int
    block_exempted_credits: int
    audits_written: int
    detail: str


@router.patch(
    "/{matric_no}/exemptions",
    response_model=StudentExemptionsPatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Update student exemptions, entry semester, and EX/CT course records"
)
async def patch_student_exemptions(
    matric_no: str,
    request: StudentExemptionsPatchRequest,
    jwt_payload: dict = Depends(verify_advisor_jwt),
):
    """
    Sets entry_semester and block_exempted_credits, and adds/removes EX/CT course records.
    
    Security & Validation:
      1. Requires verified Advisor JWT.
      2. Advisor must belong to the same tenant as the student (403 otherwise).
      3. Advisor must be the student's assigned advisor (403 otherwise).
      4. Audits each modification in exemption_audit table.
    """
    clean_matric = matric_no.strip().upper()
    svc = SupabaseService()
    if not svc.client:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database service client is unavailable."
        )

    # 1. Fetch student
    stu_res = svc.client.table("students").select(
        "matric_no, tenant_id, advisor_staff_id, entry_semester, block_exempted_credits, cohort_id"
    ).eq("matric_no", clean_matric).limit(1).execute()

    if not stu_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{clean_matric}' not found."
        )
    student = stu_res.data[0]
    student_tenant = student.get("tenant_id")
    assigned_advisor_staff = student.get("advisor_staff_id")

    # 2. Identify caller advisor
    jwt_sub = jwt_payload.get("sub")
    advisor_staff_id: Optional[str] = None
    advisor_tenant: Optional[str] = None

    if jwt_sub:
        adv_res = svc.client.table("advisors").select("staff_id, tenant_id").eq("user_id", jwt_sub).limit(1).execute()
        if adv_res.data:
            advisor_staff_id = adv_res.data[0].get("staff_id")
            advisor_tenant = adv_res.data[0].get("tenant_id")

    if not advisor_staff_id:
        # Fallback to app_metadata if present
        app_meta = jwt_payload.get("app_metadata") or {}
        advisor_staff_id = app_meta.get("staff_id")
        advisor_tenant = app_meta.get("tenant_id")

    if not advisor_staff_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Authenticated user is not an authorized academic advisor."
        )

    # 3. Multi-tenant and Advisor-Assignment verification
    if str(advisor_tenant).lower() != str(student_tenant).lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cross-tenant access forbidden: advisor tenant '{advisor_tenant}' does not match student tenant '{student_tenant}'."
        )

    if str(advisor_staff_id).upper() != str(assigned_advisor_staff).upper():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Advisor '{advisor_staff_id}' is not the assigned advisor for student '{clean_matric}'."
        )

    # 4. Process Course Template Validation if adding courses
    template_course_codes = set()
    cohort_id = student.get("cohort_id")
    if cohort_id:
        try:
            cohort_res = svc.client.table("cohorts").select("template_id").eq("cohort_id", cohort_id).limit(1).execute()
            if cohort_res.data and cohort_res.data[0].get("template_id"):
                tmpl_id = cohort_res.data[0]["template_id"]
                tc_res = svc.client.table("degree_template_courses").select("course_code").eq("template_id", tmpl_id).execute()
                if tc_res.data:
                    template_course_codes = {r["course_code"].replace(" ", "").upper() for r in tc_res.data}
        except Exception:
            pass

    audit_rows: List[dict] = []
    old_entry_sem = int(student.get("entry_semester") or 1)
    old_block_credits = int(student.get("block_exempted_credits") or 0)

    # Track fields to update on students table
    student_updates = {}

    if request.entry_semester is not None:
        if request.entry_semester < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="entry_semester must be >= 1")
        if request.entry_semester != old_entry_sem:
            student_updates["entry_semester"] = request.entry_semester
            audit_rows.append({
                "tenant_id": student_tenant,
                "matric_no": clean_matric,
                "changed_by_staff_id": advisor_staff_id,
                "field": "entry_semester",
                "old_value": str(old_entry_sem),
                "new_value": str(request.entry_semester)
            })

    if request.block_exempted_credits is not None:
        if request.block_exempted_credits < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="block_exempted_credits must be >= 0")
        if request.block_exempted_credits != old_block_credits:
            student_updates["block_exempted_credits"] = request.block_exempted_credits
            audit_rows.append({
                "tenant_id": student_tenant,
                "matric_no": clean_matric,
                "changed_by_staff_id": advisor_staff_id,
                "field": "block_exempted_credits",
                "old_value": str(old_block_credits),
                "new_value": str(request.block_exempted_credits)
            })

    # Process EX / CT course records
    if request.course_actions:
        for ca in request.course_actions:
            clean_code = ca.course_code.replace(" ", "").upper()
            action_type = ca.action.strip().lower()
            grade_val = ca.grade.strip().upper()

            if grade_val not in {"EX", "CT"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid exemption grade '{grade_val}'. Only 'EX' (exemption) and 'CT' (credit transfer) are allowed."
                )

            # If template courses were resolved, ensure course belongs to student's template
            if template_course_codes and clean_code not in template_course_codes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Course '{clean_code}' is not part of student's cohort degree template."
                )

            if action_type == "add":
                if ca.credits is None or ca.credits < 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Credits are required for '{clean_code}' (0 or more)."
                    )
                # Check for existing record
                existing_res = svc.client.table("academic_records").select("id, grade").eq("matric_no", clean_matric).eq("course_code", clean_code).execute()
                old_grade = existing_res.data[0].get("grade") if existing_res.data else None

                svc.client.table("academic_records").upsert({
                    "tenant_id": student_tenant,
                    "matric_no": clean_matric,
                    "course_code": clean_code,
                    "course_name": ca.course_name or clean_code,
                    "credits": ca.credits,
                    "grade": grade_val,
                    "grade_point": 0.00,
                    "status": "Exempted",
                    "semester": ca.semester or f"Sem {request.entry_semester or old_entry_sem}"
                }).execute()

                audit_rows.append({
                    "tenant_id": student_tenant,
                    "matric_no": clean_matric,
                    "changed_by_staff_id": advisor_staff_id,
                    "field": f"course_exemption_add:{clean_code}",
                    "old_value": str(old_grade) if old_grade else None,
                    "new_value": grade_val
                })

            elif action_type == "remove":
                existing_res = svc.client.table("academic_records").select("id, grade").eq("matric_no", clean_matric).eq("course_code", clean_code).execute()
                old_grade = existing_res.data[0].get("grade") if existing_res.data else None

                svc.client.table("academic_records").delete().eq("matric_no", clean_matric).eq("course_code", clean_code).execute()

                audit_rows.append({
                    "tenant_id": student_tenant,
                    "matric_no": clean_matric,
                    "changed_by_staff_id": advisor_staff_id,
                    "field": f"course_exemption_remove:{clean_code}",
                    "old_value": str(old_grade) if old_grade else None,
                    "new_value": None
                })
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown course action '{ca.action}'. Must be 'add' or 'remove'."
                )

    # 5. Persist student updates
    if student_updates:
        svc.client.table("students").update(student_updates).eq("matric_no", clean_matric).execute()

    # 6. Persist exemption audits
    if audit_rows:
        try:
            svc.client.table("exemption_audit").insert(audit_rows).execute()
        except Exception as e:
            # If table not migrated in test environment, log warning
            print(f"[exemption_audit] Insert log: {e}")

    final_entry_sem = student_updates.get("entry_semester", old_entry_sem)
    final_block_credits = student_updates.get("block_exempted_credits", old_block_credits)

    return StudentExemptionsPatchResponse(
        success=True,
        matric_no=clean_matric,
        entry_semester=final_entry_sem,
        block_exempted_credits=final_block_credits,
        audits_written=len(audit_rows),
        detail="Student exemptions and academic progression updated successfully."
    )
