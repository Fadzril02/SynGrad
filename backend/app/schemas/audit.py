"""
Smart Academic Assessment System - Audit & Ingestion Schemas
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class TranscriptProcessRequest(BaseModel):
    """
    Dynamic Multi-Tenant Request model for processing a transcript from storage.
    """
    tenant_id: Optional[str] = Field(None, description="Institutional multi-tenant identifier (deprecated: extracted server-side from JWT)")
    storage_path: str = Field(..., description="Path inside the transcripts bucket")
    student_id: Optional[str] = Field(None, description="UUID of existing student, or None to auto-create/lookup via matric")
    advisor_id: str = Field(..., description="UUID of authenticated advisor")
    university_id: str = Field(..., description="UUID of the university")
    matric_number: Optional[str] = Field(None, description="Student matric number if known upfront")
    curriculum_year: Optional[str] = Field(None, description="Curriculum intake year")
    program_code: Optional[str] = Field(None, description="Program code")
    cohort_id: Optional[str] = Field(None, description="UUID of student's cohort")


class ExtractPDFRequest(BaseModel):
    file_path: str = Field(..., description="Path in Supabase storage bucket, e.g. 'slips/matric_timestamp.pdf'")
    tenant_id: Optional[str] = Field(None, description="Tenant ID identifier (deprecated: extracted server-side from JWT)")


class ExtractPDFResponse(BaseModel):
    success: bool
    data: Dict[str, Any]


class ParsedLineItem(BaseModel):
    course_code: str
    course_name: str
    credits: int
    grade: str
    grade_point: float
    semester: Optional[str] = None
    status: str  # 'Passed', 'Failed', 'Exempted', 'In-Progress'
    warning: Optional[str] = None
    is_ai_parsed: bool = False
    raw_extracted_text: Optional[str] = None


class CourseAuditResult(BaseModel):
    course_code: str
    course_name: str
    credits: int
    grade: str
    grade_point: float
    semester: Optional[str] = None
    status: str
    warning: Optional[str] = None
    domain: str = "Core Development"  # Logic & Math, Core Development, Systems & Architecture, Soft Skills, Project Management
    traffic_light: str  # 'GREEN', 'YELLOW', 'RED'
    prerequisite_met: bool
    missing_prerequisites: List[str] = []
    is_ai_parsed: bool = False
    raw_extracted_text: Optional[str] = None


class AuditSummary(BaseModel):
    total_credits_required: int = 0
    total_credits_earned: int = 0
    cgpa: float = 0.00
    overall_traffic_light: str = "GREEN"  # 'GREEN', 'YELLOW', 'RED'
    passed_courses_count: int = 0
    failed_courses_count: int = 0
    in_progress_courses_count: int = 0
    unmet_prerequisites_count: int = 0
    academic_standing: str = "Good Standing"
    ai_fallback_used: bool = False
    cgpa_warning: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    radar_stats: Dict[str, float] = Field(
        default_factory=lambda: {
            "Logic & Math": 0.0,
            "Core Development": 0.0,
            "Systems & Architecture": 0.0,
            "Soft Skills": 0.0,
            "Project Management": 0.0,
        }
    )


class DegreeAuditResponse(BaseModel):
    audit_id: Optional[str] = None
    student_id: str
    matric_number: str
    student_name: str
    university_id: str
    advisor_id: str
    summary: AuditSummary
    records: List[CourseAuditResult]
    unparsed_lines: List[str] = []


class ExtractedCourseItem(BaseModel):
    course_code: str
    course_name: Optional[str] = "Course"
    grade: str
    # Any so finalize-approval can list every bad row in one 422 instead of a generic schema error
    credit_hour: Optional[Any] = None
    credits: Optional[Any] = None
    status: Optional[str] = "Pass"
    warning: Optional[str] = None
    session_semester: Optional[str] = None


class FinalizeApprovalRequest(BaseModel):
    tenant_id: Optional[str] = Field(None, description="Multi-tenant identifier (deprecated: extracted server-side from JWT)")
    document_id: str = Field(..., description="UUID of document in uploaded_documents table")
    matric_number: str = Field(..., description="Student matric number")
    student_name: Optional[str] = None
    advisor_id: Optional[str] = Field(None, description="Advisor staff ID (extracted server-side from JWT)")
    university_id: Optional[str] = ""
    curriculum_year: Optional[str] = None
    program_code: Optional[str] = None
    cohort_id: Optional[str] = Field(None, description="UUID of student's cohort")
    academic_session: Optional[str] = Field(None, description="Academic session e.g. 2024/2025")
    semester: Optional[Any] = Field(None, description="Semester number 1-4")
    pngk: Optional[float] = Field(None, description="Cumulative GPA printed on transcript for verification")
    courses: List[ExtractedCourseItem] = []
    storage_path: Optional[str] = Field(None, description="Optional storage path of the transcript file to purge")
    file_path: Optional[str] = Field(None, description="Optional file path of the transcript file to purge")


class AuditApprovalRequest(BaseModel):
    """
    Dynamic Multi-Tenant Request model for finalizing advisor audit approval.
    """
    tenant_id: Optional[str] = Field(None, description="Institutional multi-tenant identifier (deprecated: extracted server-side from JWT)")
    document_id: str = Field(..., description="UUID of document in uploaded_documents table")
    matric_number: str = Field(..., description="Student matric number")
    student_name: Optional[str] = None
    advisor_id: Optional[str] = Field(None, description="Advisor staff ID (extracted server-side from JWT)")
    university_id: Optional[str] = ""
    curriculum_year: Optional[str] = None
    program_code: Optional[str] = None
    cohort_id: Optional[str] = Field(None, description="UUID of student's cohort")
    academic_session: Optional[str] = Field(None, description="Academic session e.g. 2024/2025")
    semester: Optional[Any] = Field(None, description="Semester number 1-4")
    pngk: Optional[float] = Field(None, description="Cumulative GPA printed on transcript for verification")
    courses: List[ExtractedCourseItem] = []
    storage_path: Optional[str] = Field(None, description="Optional storage path of the transcript file to purge")
    file_path: Optional[str] = Field(None, description="Optional file path of the transcript file to purge")


class FinalizeApprovalResponse(BaseModel):
    success: bool
    audit_id: str
    document_id: str
    matric_number: str
    student_name: str
    summary: AuditSummary
    records_saved_count: int
    processing_status: str = "Approved"
    records: List[CourseAuditResult]
    storage_purged: bool = False
    warning: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class PurgeDocumentRequest(BaseModel):
    document_id: Optional[str] = Field(None, description="UUID of target uploaded document")
    matric_no: Optional[str] = Field(None, description="Student matric number")
    admin_staff_id: Optional[str] = Field("ADMIN", description="Staff ID of administrator triggering the purge")


class PurgeDocumentResponse(BaseModel):
    success: bool
    message: str
    document_id: str
    purged_file_path: Optional[str] = None
    storage_deleted: bool = False
    processing_status: str


class SubmitVerificationRequest(BaseModel):
    document_id: str = Field(..., description="UUID of the uploaded document being verified by the student")
    courses: List[Dict[str, Any]] = Field(..., description="Student-reviewed course rows (same order as extracted rows)")


class RejectDocumentRequest(BaseModel):
    document_id: str = Field(..., description="UUID of target uploaded document to reject")
    rejection_reason: Optional[str] = Field("Document rejected by advisor", description="Reason for document rejection")
    advisor_id: Optional[str] = Field(None, description="Advisor staff ID")


class RejectDocumentResponse(BaseModel):
    success: bool
    document_id: str
    processing_status: str = "Rejected"
    message: str


class ElectiveOverrideRequest(BaseModel):
    kind: str = Field(..., description="'assign' or 'exclude'")
    course_code: str = Field(..., description="Course code of passing attempt")
    template_course_id: Optional[str] = Field(None, description="UUID of template course (required if kind='assign')")
    note: Optional[str] = Field(None, description="Optional advisor note")

