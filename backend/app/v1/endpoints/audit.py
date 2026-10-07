"""
Smart Academic Assessment System - Degree Audit Processing Endpoints
"""

import uuid
import asyncio
import time
import logging
import fitz  # PyMuPDF
from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any, List, Optional

logger = logging.getLogger("app.v1.endpoints.audit")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


try:
    from app.schemas.audit import (
        TranscriptProcessRequest,
        DegreeAuditResponse,
        AuditSummary,
        CourseAuditResult,
        PurgeDocumentRequest,
        PurgeDocumentResponse,
        FinalizeApprovalRequest,
        AuditApprovalRequest,
        FinalizeApprovalResponse,
        ExtractPDFRequest,
        ExtractPDFResponse,
        ParsedLineItem,
        RejectDocumentRequest,
        SubmitVerificationRequest,
        RejectDocumentResponse,
        ElectiveOverrideRequest,
    )
    from app.engine.extractor import PDFExtractor
    from app.engine.parsers.malaysian_regex import MalaysianTranscriptParser
    from app.engine.grading import load_scale, GradingScale, normalize_semester, select_attempts_by_repeat_policy
    from app.engine.graph_resolver import PrerequisiteGraphResolver
    from app.engine.llm_fallback import MicroLLMFallback
    from app.engine.universal_reader import extract_with_llm
    from app.engine.slip_validation import validate_slip
    from app.engine.progress import compute_progress
    from app.core.config import settings
    from app.core.supabase_client import SupabaseService
    from app.core.auth import verify_advisor_jwt
except ImportError:
    from backend.app.schemas.audit import (
        TranscriptProcessRequest,
        DegreeAuditResponse,
        AuditSummary,
        CourseAuditResult,
        PurgeDocumentRequest,
        PurgeDocumentResponse,
        FinalizeApprovalRequest,
        AuditApprovalRequest,
        FinalizeApprovalResponse,
        ExtractPDFRequest,
        ExtractPDFResponse,
        ParsedLineItem,
        RejectDocumentRequest,
        SubmitVerificationRequest,
        RejectDocumentResponse,
        ElectiveOverrideRequest,
    )
    from backend.app.engine.extractor import PDFExtractor
    from backend.app.engine.parsers.malaysian_regex import MalaysianTranscriptParser
    from backend.app.engine.grading import load_scale, GradingScale, normalize_semester, select_attempts_by_repeat_policy
    from backend.app.engine.graph_resolver import PrerequisiteGraphResolver
    from backend.app.engine.llm_fallback import MicroLLMFallback
    from backend.app.engine.universal_reader import extract_with_llm
    from backend.app.engine.slip_validation import validate_slip
    from backend.app.engine.progress import compute_progress
    from backend.app.core.config import settings
    from backend.app.core.supabase_client import SupabaseService
    from backend.app.core.auth import verify_advisor_jwt

router = APIRouter(prefix="/audit", tags=["Degree Audit"])


async def _to_thread_retry(fn, *args, **kwargs):
    """Run a sync Supabase call in a thread; retry ONCE on transport errors.

    Supabase/HTTP2 may drop an idle or concurrently-used connection
    ("Server disconnected"). Reads are idempotent, so one retry is safe.
    Non-transport errors (HTTPException, APIError) propagate unchanged.
    """
    import httpx
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except httpx.TransportError as e:
        logger.warning(f"[Progress] transport error, retrying once: {e!r}")
        await asyncio.sleep(0.2)
        return await asyncio.to_thread(fn, *args, **kwargs)


def _load_repeat_policy(tenant_id: str) -> str:
    """Fail loud: a tenant without a readable repeat_policy is a config error, never default."""
    import httpx
    def _q():
        return supabase_svc.client.table("tenants").select("repeat_policy").eq("id", tenant_id).limit(1).execute()
    try:
        try:
            t_res = _q()
        except httpx.TransportError:
            # Supabase may drop a shared HTTP/2 connection (GOAWAY / ConnectionTerminated). Read is idempotent: retry once.
            t_res = _q()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Could not load tenant settings: {e}")
    policy = (t_res.data[0].get("repeat_policy") if t_res.data else None)
    if not policy:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Tenant '{tenant_id}' has no repeat_policy configured.")
    return policy


def _load_tenant_slip_profile(tenant_id: str) -> Optional[str]:
    """Loads tenant slip_profile ('utm' vs None for universal reader)."""
    import httpx
    def _q():
        return supabase_svc.client.table("tenants").select("slip_profile").eq("id", tenant_id).limit(1).execute()
    try:
        try:
            res = _q()
        except httpx.TransportError:
            res = _q()
        if res and res.data and len(res.data) > 0:
            return res.data[0].get("slip_profile")
    except Exception as e:
        logger.warning(f"Could not load tenant slip_profile: {e}")
    return None


supabase_svc = SupabaseService()


def _load_authorized_document(
    jwt_payload: dict,
    *,
    file_path: Optional[str] = None,
    document_id: Optional[str] = None,
    allow_student: bool = True,
    allow_advisor: bool = True,
    expected_matric: Optional[str] = None,
):
    """
    Load an uploaded_documents row and verify the caller may act on it.
    Student: owns the matric (students.user_id = JWT sub).
    Advisor: is the student's assigned advisor in the same tenant.
    Returns (doc, role). Raises 401/403/404 (fail loud, never guess).
    """
    jwt_sub = jwt_payload.get("sub")
    if not jwt_sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing subject (sub)")
    if not supabase_svc.client:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database client unavailable")
    if not file_path and not document_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file_path or document_id is required")

    q = supabase_svc.client.table("uploaded_documents").select(
        "id, matric_no, file_path, processing_status, extracted_data, fraud_flag"
    )
    q = q.eq("id", document_id) if document_id else q.eq("file_path", file_path)
    res = q.limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    doc = res.data[0]

    if expected_matric and expected_matric.strip().upper() != str(doc.get("matric_no") or "").strip().upper():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="matric_number does not match the document",
        )

    stu = (
        supabase_svc.client.table("students")
        .select("user_id, advisor_staff_id, tenant_id")
        .eq("matric_no", doc["matric_no"])
        .limit(1)
        .execute()
    )
    if not stu.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this document")
    student = stu.data[0]

    if allow_student and student.get("user_id") == jwt_sub:
        return doc, "student"

    if allow_advisor:
        adv = (
            supabase_svc.client.table("advisors")
            .select("staff_id, tenant_id")
            .eq("user_id", jwt_sub)
            .limit(1)
            .execute()
        )
        if (
            adv.data
            and adv.data[0].get("staff_id") == student.get("advisor_staff_id")
            and adv.data[0].get("tenant_id") == student.get("tenant_id")
        ):
            return doc, "advisor"

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this document")


def _mark_document_failed(document_id: str, message: str) -> None:
    """Record an extraction failure server-side (students can no longer write this)."""
    try:
        supabase_svc.client.table("uploaded_documents").update({
            "processing_status": "Extraction_Failed",
            "processing_error": (message or "Extraction failed")[:500],
        }).eq("id", document_id).execute()
    except Exception as e:
        print(f"[Extract] Failed to mark document {document_id} as Extraction_Failed: {e}")
llm_fallback = MicroLLMFallback()

def fetch_and_merge_historical_records(matric_no: str, new_records: List[ParsedLineItem], tenant_id: str) -> List[ParsedLineItem]:
    if not supabase_svc.client or not matric_no:
        return new_records
    try:
        # MULTI-TENANT: scope fetch to (tenant_id, matric_no) so we never
        # cross tenant boundaries when pulling the cumulative history.
        res = (
            supabase_svc.client
            .table("academic_records")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("matric_no", matric_no)
            .execute()
        )
        existing = res.data or []
    except Exception as e:
        print(f"[Merge Historical] Error fetching historical records: {e}")
        existing = []

    # Map of incoming records: (clean_course_code, normalized_semester)
    new_keys = set()
    for nr in new_records:
        c_code = nr.course_code.replace(" ", "").upper()
        c_sem = normalize_semester(nr.semester) if nr.semester else ""
        if c_code and c_sem:
            new_keys.add((c_code, c_sem))

    merged = []
    for r in existing:
        ex_code = (r.get("course_code") or "").replace(" ", "").upper()
        raw_sem = r.get("semester")
        ex_sem = normalize_semester(raw_sem) if raw_sem else ""
        # Keep existing row unless an incoming new record matches on (course_code, normalised semester)
        if (ex_code, ex_sem) not in new_keys:
            merged.append(ParsedLineItem(
                course_code=r.get("course_code"),
                course_name=r.get("course_name") or r.get("course_code"),
                credits=r.get("credits") or 3,
                grade=r.get("grade"),
                grade_point=float(r.get("grade_point") or 0.0),
                semester=ex_sem or raw_sem,
                status=r.get("status"),
                warning=r.get("warning"),
                is_ai_parsed=r.get("is_ai_parsed", False),
                raw_extracted_text=r.get("raw_extracted_text", "")
            ))
    return merged + new_records


def _extract_advisor_id(jwt_payload: dict) -> str:
    """
    Extract advisor staff_id server-side strictly from verified JWT app_metadata
    or by querying the advisors table using the verified sub claim.
    Completely removes all references to user_metadata or unverified payload.
    Hard-fails with 403 Forbidden if not securely verified.
    """
    app_metadata = jwt_payload.get("app_metadata") or {}
    advisor_id = app_metadata.get("staff_id") or app_metadata.get("advisor_id")
    if advisor_id and str(advisor_id).strip():
        return str(advisor_id).strip()

    jwt_sub = jwt_payload.get("sub")
    if supabase_svc.client and jwt_sub:
        try:
            res = (
                supabase_svc.client.table("advisors")
                .select("staff_id")
                .eq("user_id", jwt_sub)
                .limit(1)
                .execute()
            )
            if res.data and len(res.data) > 0 and res.data[0].get("staff_id"):
                return str(res.data[0]["staff_id"]).strip()
        except Exception as e:
            print(f"[_extract_advisor_id] Advisor staff_id lookup error: {e}")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Unauthorized: Advisor identity cannot be securely verified."
    )


def _check_advisor_identity(jwt_payload: dict, claimed_advisor_id: str) -> str:
    """
    Cross-reference the verified JWT advisor identity against the advisor_id
    claimed in the request body.
    """
    actual_staff_id = _extract_advisor_id(jwt_payload)
    if actual_staff_id != claimed_advisor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"JWT identity (staff_id='{actual_staff_id}') does not match "
                f"the claimed advisor_id='{claimed_advisor_id}' in the request body."
            ),
        )
    return actual_staff_id


UTM_SEEDED_UUID = "00000000-0000-0000-0000-000000000001"


def _resolve_university_code(university_id_or_code: str) -> Optional[str]:
    """
    Resolves raw tenant_id or university_id into an institutional code string (e.g. 'UTM').
    - If the value is a known institution code or alphanumeric short code, returns it directly.
    - If it is a UUID:
      * If it matches the seeded UTM UUID ('00000000-0000-0000-0000-000000000001'), returns 'UTM'.
      * Otherwise queries 'universities' table (select code from universities where id = university_id)
        to resolve the actual institution code.
      * Falls back to 'UTM' if the resolved code is empty or lookup fails.
    """
    raw_val = str(university_id_or_code).strip()
    if not raw_val:
        return None

    is_uuid = False
    try:
        uuid.UUID(raw_val)
        is_uuid = True
    except (ValueError, AttributeError, TypeError):
        is_uuid = False

    if not is_uuid:
        return raw_val

    if raw_val.lower() == UTM_SEEDED_UUID.lower():
        return "UTM"

    if supabase_svc.client:
        try:
            res = (
                supabase_svc.client.table("universities")
                .select("code")
                .eq("id", raw_val)
                .limit(1)
                .execute()
            )
            if res.data and len(res.data) > 0 and res.data[0].get("code"):
                resolved_code = str(res.data[0]["code"]).strip()
                if resolved_code:
                    return resolved_code
        except Exception as e:
            print(f"[_resolve_university_code] University code lookup error: {e}")

    return None


def _extract_tenant_id(jwt_payload: dict) -> str:
    """
    Extract tenant_id server-side strictly from verified JWT app_metadata
    or by querying the advisors table using the verified sub claim.
    Resolves UUIDs to institutional codes (e.g. 'UTM') via the universities table.
    Completely removes all references to user_metadata or unverified payload.
    Hard-fails with 403 Forbidden if not securely verified.
    """
    app_metadata = jwt_payload.get("app_metadata") or {}
    tenant_val = app_metadata.get("tenant_id") or app_metadata.get("university_id")
    if tenant_val and str(tenant_val).strip():
        resolved = _resolve_university_code(str(tenant_val).strip())
        if resolved:
            return resolved

    jwt_sub = jwt_payload.get("sub")
    if supabase_svc.client and jwt_sub:
        try:
            res = (
                supabase_svc.client.table("advisors")
                .select("tenant_id")
                .eq("user_id", jwt_sub)
                .limit(1)
                .execute()
            )
            if res.data and len(res.data) > 0 and res.data[0].get("tenant_id"):
                raw_tenant = str(res.data[0]["tenant_id"]).strip()
                resolved = _resolve_university_code(raw_tenant)
                if resolved or raw_tenant:
                    return resolved or raw_tenant
        except Exception as e:
            print(f"[_extract_tenant_id] Advisor tenant_id lookup error: {e}")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Unauthorized: Tenant ID cannot be securely verified."
    )


@router.post(
    "/extract",
    response_model=ExtractPDFResponse,
    status_code=status.HTTP_200_OK,
    summary="Extracts course grades and metadata from a transcript PDF in storage"
)
async def extract_transcript_from_storage(
    request: ExtractPDFRequest,
    jwt_payload: dict = Depends(verify_advisor_jwt),
):
    """
    Zero-Waste Fast Extraction:
    1. Downloads PDF from Supabase storage ('academic-slips' / 'transcripts').
    2. Inspects PDF metadata for suspicious editing software (fraud detection).
    3. Runs in-memory PyMuPDF text extraction (<50ms).
    4. Parses course codes, grades, credits via Malaysian regex parser.
    5. Falls back to micro-LLM only for ambiguous/unparsed transfer lines.
    6. Updates uploaded_documents with extracted_data & fraud_flag.
    """
    doc, role = _load_authorized_document(jwt_payload, file_path=request.file_path)
    try:
        return await _extract_core(request, jwt_payload, doc, role)
    except HTTPException as he:
        _mark_document_failed(doc["id"], str(he.detail))
        raise
    except Exception as e:
        _mark_document_failed(doc["id"], str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Extraction failed unexpectedly. Please retry.",
        )


async def _extract_core(request: ExtractPDFRequest, jwt_payload: dict, doc: dict, role: str) -> ExtractPDFResponse:
    try:
        pdf_bytes = supabase_svc.download_transcript_bytes(request.file_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to download PDF from '{request.file_path}': {str(e)}"
        )

    # 1. Check Metadata for Digital Forgery
    is_fraudulent = False
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf_doc:
            meta = pdf_doc.metadata or {}
            creator = (meta.get("creator") or "").lower()
            producer = (meta.get("producer") or "").lower()
            suspicious = ['adobe illustrator', 'photoshop', 'canva', 'ilovepdf', 'microsoft', 'word', 'google']
            if any(s in creator for s in suspicious) or any(s in producer for s in suspicious):
                is_fraudulent = True
    except Exception:
        pass

    # 2. Extract Text Lines
    try:
        raw_lines = PDFExtractor.extract_text_lines_from_bytes(pdf_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to extract text from PDF: {str(e)}"
        )

    if not raw_lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Scanned slips aren't supported yet — please upload the original PDF from your student portal."
        )

    # 2b. Load tenant grading scale & slip profile
    tenant_id = _extract_tenant_id(jwt_payload)
    slip_profile = _load_tenant_slip_profile(tenant_id)
    expected_matric = doc.get("matric_no")

    try:
        scale = load_scale(tenant_id, client=supabase_svc.client)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve)
        )

    use_rules = False
    rule_metadata: Dict[str, Any] = {}
    rule_courses = []

    if slip_profile == "utm":
        try:
            rule_metadata, rule_courses, unparsed_lines = MalaysianTranscriptParser.parse_transcript_lines(raw_lines, scale=scale)
            has_sem = rule_metadata.get("semester") is not None
            has_sess = bool(rule_metadata.get("academic_session"))
            has_courses = len(rule_courses) >= 1
            no_unparsed = len(unparsed_lines) == 0

            if has_sem and has_sess and has_courses and no_unparsed:
                use_rules = True
        except Exception as e:
            logger.warning(f"[Extract] Rule parser error: {e}")
            use_rules = False

    if use_rules:
        source = "rules"
        model = None
        sem_num = rule_metadata.get("semester")
        session_name = rule_metadata.get("academic_session")
        try:
            norm_sem = normalize_semester(f"SEM {sem_num} {session_name}")
        except Exception:
            norm_sem = f"SEM {sem_num} {session_name}"

        courses_payload = [
            {
                "course_code": c.course_code,
                "course_name": c.course_name,
                "grade": c.grade,
                "credit_hour": c.credits,
                "credits": c.credits,
                "status": c.status,
                "warning": c.warning,
                "session_semester": c.semester or norm_sem,
                "is_ai_parsed": False,
            }
            for c in rule_courses
        ]

        semesters_list = [
            {
                "semester_no": sem_num,
                "session": session_name,
                "courses": courses_payload,
                "printed_gpa": rule_metadata.get("png"),
                "printed_cgpa": rule_metadata.get("pngk"),
            }
        ]
        student_name = rule_metadata.get("student_name")
        matric_number = rule_metadata.get("matric_number")
        printed_gpa = rule_metadata.get("png")
        printed_cgpa = rule_metadata.get("pngk")
        kk_all_sem = rule_metadata.get("kk_all_sem")
        kd_all_sem = rule_metadata.get("kd_all_sem")
        initial_warnings = list(rule_metadata.get("warnings", []))
    else:
        # Universal AI reader path
        source = "ai"
        model = settings.LLM_MODEL
        full_text = "\n".join(raw_lines)
        tenant_ctx = {
            "tenant_id": tenant_id,
            "valid_grades": list(scale._by_grade.keys()),
        }
        try:
            ai_data = extract_with_llm(full_text, tenant_ctx)
        except HTTPException:
            raise
        except Exception as ai_err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Universal slip reader failed: {ai_err}",
            )

        semesters_data = ai_data.get("semesters", [])
        matric_number = ai_data.get("matric_no")
        student_name = None

        courses_payload = []
        semesters_list = []

        for sem_obj in semesters_data:
            s_num = sem_obj.get("semester_no", 1)
            s_sess = sem_obj.get("session", "")
            try:
                norm_s = normalize_semester(f"SEM {s_num} {s_sess}")
            except Exception:
                norm_s = f"SEM {s_num} {s_sess}"

            sem_courses_payload = []
            for c in sem_obj.get("courses", []):
                c_code = c.get("code", "").replace(" ", "").upper()
                c_grade = c.get("grade", "").strip().upper()
                c_creds = c.get("credits", 3)

                try:
                    is_p = scale.is_pass(c_grade, c_code)
                    in_cgpa = scale.counts_in_cgpa(c_grade, c_code)
                    as_comp = scale.counts_as_completed(c_grade, c_code)
                    if is_p and not in_cgpa and as_comp:
                        c_status = "Exempted"
                    elif is_p:
                        c_status = "Passed"
                    elif c_grade in {"TD", "TS"}:
                        c_status = "In-Progress"
                    else:
                        c_status = "Failed"
                except Exception:
                    c_status = "Passed" if c_grade in {"A+", "A", "A-", "B+", "B", "B-", "C+", "C"} else "Failed"

                c_creds_val = int(c_creds) if isinstance(c_creds, (int, float)) and float(c_creds).is_integer() else c_creds

                item_dict = {
                    "course_code": c_code,
                    "course_name": c.get("name", c_code),
                    "grade": c_grade,
                    "credit_hour": c_creds_val,
                    "credits": c_creds_val,
                    "status": c_status,
                    "warning": None,
                    "session_semester": norm_s,
                    "is_ai_parsed": True,
                }
                sem_courses_payload.append(item_dict)
                courses_payload.append(item_dict)

            semesters_list.append({
                "semester_no": s_num,
                "session": s_sess,
                "courses": sem_courses_payload,
                "printed_gpa": sem_obj.get("printed_gpa"),
                "printed_cgpa": sem_obj.get("printed_cgpa"),
            })

        if semesters_list:
            sem_num = semesters_list[0]["semester_no"]
            session_name = semesters_list[0]["session"]
            printed_gpa = semesters_list[0]["printed_gpa"]
            printed_cgpa = semesters_list[0]["printed_cgpa"]
        else:
            sem_num = None
            session_name = None
            printed_gpa = None
            printed_cgpa = None

        kk_all_sem = None
        kd_all_sem = None
        initial_warnings = []

    # Run Guardrails on result
    guardrail_warnings, needs_review = validate_slip(
        {
            "semesters": semesters_list,
            "matric_no": matric_number,
        },
        scale=scale,
        expected_matric=expected_matric,
    )
    for w in guardrail_warnings:
        if w not in initial_warnings:
            initial_warnings.append(w)

    gpa_warning = next((w for w in initial_warnings if "GPA mismatch" in w), None)

    extracted_data = {
        "source": source,
        "model": model,
        "warnings": initial_warnings,
        "needs_review": needs_review or len(initial_warnings) > 0,
        "semesters": semesters_list,
        "academic_session": session_name,
        "semester": sem_num,
        "courses": courses_payload,
        "matric_number": matric_number,
        "student_name": student_name,
        "fraud_flag": is_fraudulent,
        "png": printed_gpa,
        "pngk": printed_cgpa,
        "gpa": printed_gpa,
        "cgpa": printed_cgpa,
        "kk_all_sem": kk_all_sem,
        "kd_all_sem": kd_all_sem,
        "gpa_warning": gpa_warning,
    }

    # 6. Persist server-side (the browser never writes extracted grades)
    extracted_data["original_courses"] = courses_payload
    update_payload = {
        "extracted_data": extracted_data,
        "fraud_flag": is_fraudulent,
        "processing_error": None,
    }
    if role == "student":
        # Student re-extraction restarts verification; advisor extraction never changes status
        update_payload["processing_status"] = "Pending_Student_Verification"
    try:
        supabase_svc.client.table("uploaded_documents").update(update_payload).eq("id", doc["id"]).execute()
    except Exception as update_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save extracted data: {update_err}",
        )


    return ExtractPDFResponse(success=True, data=extracted_data)


@router.post(
    "/finalize-approval",
    response_model=FinalizeApprovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Finalizes advisor approval: runs DAG audit, saves to academic_records, updates status to Approved"
)
async def finalize_approval(
    request: FinalizeApprovalRequest,
    jwt_payload: dict = Depends(verify_advisor_jwt),
):
    """
    Advisor Approval Finalization:
    1. Converts staged courses to normalized ParsedLineItem models.
    2. Fetches course catalog with prerequisite and min_grade rules.
    3. Runs PrerequisiteGraphResolver (DAG graph, min_grade verification, traffic light matrix).
    4. Persists records to 'academic_records' and full snapshot to 'degree_audits'.
    5. Updates student CGPA & academic standing in 'students'.
    6. Updates uploaded_documents row to processing_status = 'Approved'.
    """
    # Stop trusting frontend for advisor identity. Extract advisor_id and tenant_id strictly from verified JWT app_metadata or verified sub DB lookup.
    advisor_id = _extract_advisor_id(jwt_payload)
    tenant_id = _extract_tenant_id(jwt_payload)

    # Only the student's own advisor may approve, and the matric must match the document
    _load_authorized_document(
        jwt_payload,
        document_id=request.document_id,
        allow_student=False,
        expected_matric=request.matric_number,
    )

    # Validate that courses array is not empty
    if not request.courses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No course records provided for approval."
        )

    matric_number = (request.matric_number or "").strip()
    if not matric_number:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Student matric_number is required and cannot be empty."
        )

    repeat_policy = _load_repeat_policy(tenant_id)

    # Validate explicit semester and academic session (Requirement: missing semester/session -> 422, no fallback)
    if request.semester is None or str(request.semester).strip() == "" or not request.academic_session or str(request.academic_session).strip() == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required semester or academic_session. Both must be explicitly specified."
        )

    # 1. Transform Staged Courses into ParsedLineItem objects using Tenant Grading Scale
    try:
        scale = load_scale(tenant_id, client=supabase_svc.client)

        raw_current_sem = f"Sem {request.semester} {request.academic_session}".strip()
        current_semester = normalize_semester(raw_current_sem)

        parsed_items: List[ParsedLineItem] = []
        for c in request.courses:
            code = c.course_code.replace(" ", "").upper()
            grade = c.grade.strip().upper()
            credits_val = c.credits or c.credit_hour or 3
            gp = scale.grade_points(grade, code)
            is_p = scale.is_pass(grade, code)
            in_cgpa = scale.counts_in_cgpa(grade, code)
            as_comp = scale.counts_as_completed(grade, code)

            # Status determination via grading scale rules
            if is_p and not in_cgpa and as_comp:
                item_status = "Exempted"
            elif is_p:
                item_status = "Passed"
            elif grade in {"TD", "TS"}:
                item_status = "In-Progress"
            else:
                item_status = "Failed"

            # Use c.session_semester if specified, else current_semester; normalize it
            raw_item_sem = c.session_semester.strip() if c.session_semester and c.session_semester.strip() else current_semester
            norm_item_sem = normalize_semester(raw_item_sem)

            parsed_items.append(ParsedLineItem(
                course_code=code,
                course_name=c.course_name or code,
                credits=credits_val,
                grade=grade,
                grade_point=gp,
                semester=norm_item_sem,
                status=item_status,
                warning=getattr(c, "warning", None),
                is_ai_parsed=False,
                raw_extracted_text=f"[ADVISOR APPROVED] {code} {grade} ({credits_val} cr)"
            ))

        # 2. Fetch Course Catalog & Prerequisite Graph for University
        catalog = supabase_svc.get_university_course_catalog(request.university_id)

        # 3. Fetch student's degree_template via cohort_id & extract total_credits_required
        total_required_credits = supabase_svc.get_student_required_credits(
            matric_no=matric_number,
            cohort_id=getattr(request, "cohort_id", None),
            program_code=request.program_code,
            curriculum_year=request.curriculum_year
        )

        # 3a. Fetch block_exempted_credits and graduation_credit_requirement from students table.
        block_exempted_credits, student_grad_req = supabase_svc.get_student_block_exempted_credits(
            matric_no=matric_number
        )
        if student_grad_req is not None:
            total_required_credits = student_grad_req

        # 3b. SECURE MULTI-TENANCY (Prevent IDOR):
        # Historical records scoped to verified tenant_id derived server-side
        parsed_items = fetch_and_merge_historical_records(matric_number, parsed_items, tenant_id=tenant_id)

        # 4. Run Pure Python Graph Prerequisite Audit (with min_grade & credit gates)
        display_results, summary, all_audited_records = PrerequisiteGraphResolver.audit_student_records(
            records=parsed_items,
            course_catalog=catalog,
            total_required_credits=total_required_credits,
            block_exempted_credits=block_exempted_credits,
            scale=scale,
            repeat_policy=repeat_policy,
            return_all_attempts=True
        )
        # Check cumulative CGPA against printed PNGK if provided (Never auto-correct)
        cgpa_warning: Optional[str] = None
        target_pngk = getattr(request, "pngk", None)
        if target_pngk is not None:
            try:
                target_float = float(target_pngk)
                if abs(summary.cgpa - target_float) > 0.01:
                    cgpa_warning = f"CGPA mismatch with transcript (computed {summary.cgpa:.2f} vs printed {target_float:.2f})"
            except (ValueError, TypeError):
                pass

        if cgpa_warning:
            summary.cgpa_warning = cgpa_warning
            if cgpa_warning not in summary.warnings:
                summary.warnings.append(cgpa_warning)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve)
        )

    # 4. Upsert Student Record & Persist Audits to Supabase
    student = supabase_svc.get_or_create_student(
        university_id=request.university_id,
        advisor_id=advisor_id,
        matric_number=matric_number,
        student_name=request.student_name or f"Student ({matric_number})",
        curriculum_year=request.curriculum_year,
        program_code=request.program_code
    )

    try:
        audit_id = supabase_svc.persist_audit_results(
            matric_no=matric_number,
            advisor_id=advisor_id,
            records=all_audited_records,
            summary=summary,
            storage_pdf_path=f"document:{request.document_id}",
            tenant_id=tenant_id
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve)
        )

    # 5. Update uploaded_documents status to 'Approved'
    try:
        if supabase_svc.client:
            supabase_svc.client.table("uploaded_documents").update({
                "processing_status": "Approved"
            }).eq("id", request.document_id).execute()
    except Exception as doc_update_err:
        print(f"[Document Status Update Warning] {doc_update_err}")

    # 6. Relocated Automatic Storage Purge on Advisor Approval (Zero-Waste Data Retention)
    # The file should ONLY be deleted after the advisor has visually verified it
    # and the data is successfully upserted into the database.
    purge_successful = False
    try:
        target_path = getattr(request, "storage_path", None) or getattr(request, "file_path", None)
        if not target_path and supabase_svc.client and request.document_id:
            try:
                doc_query = (
                    supabase_svc.client.table("uploaded_documents")
                    .select("file_path")
                    .eq("id", request.document_id)
                    .limit(1)
                    .execute()
                )
                if doc_query.data and doc_query.data[0].get("file_path"):
                    target_path = doc_query.data[0]["file_path"]
            except Exception as doc_fetch_err:
                print(f"[Purge Path Resolution Warning] {doc_fetch_err}")

        if target_path and target_path not in {"", "[PURGED]"}:
            _bucket = "academic-slips" if "academic-slips" in target_path else "transcripts"
            supabase_svc.delete_file_from_storage(
                bucket_name=_bucket,
                file_path=target_path
            )

        if supabase_svc.client and request.document_id:
            purge_res = supabase_svc.purge_uploaded_document_file(
                document_id=request.document_id,
                matric_no=matric_number,
                admin_staff_id=advisor_id or "ADMIN"
            )
            purge_successful = purge_res.get("success", False)
            print(f"[Automatic Purge] Document '{request.document_id}' purged successfully.")
    except Exception as purge_err:
        print(f"[Auto-Purge OUTER WARNING] Unexpected error during storage cleanup: {purge_err}")

    return FinalizeApprovalResponse(
        success=True,
        audit_id=audit_id,
        document_id=request.document_id,
        matric_number=request.matric_number,
        student_name=request.student_name or f"Student ({request.matric_number})",
        summary=summary,
        records_saved_count=len(all_audited_records),
        processing_status="Approved",
        records=display_results,
        storage_purged=purge_successful,
        warning=cgpa_warning,
        warnings=[cgpa_warning] if cgpa_warning else []
    )


@router.post(
    "/purge-document",
    response_model=PurgeDocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin purge of raw transcript PDF after advisor approval"
)
async def purge_document(
    request: PurgeDocumentRequest,
    jwt_payload: dict = Depends(verify_advisor_jwt),
):
    """
    Data Retention & Privacy Enforcement:
    1. Validates that the target document is marked 'Approved'.
    2. Deletes raw transcript PDF bytes from Supabase Storage.
    3. Sets file_path = '[PURGED]' in uploaded_documents.
    4. Records an immutable 'DELETE' entry in system_audit_logs.
    """
    try:
        res = supabase_svc.purge_uploaded_document_file(
            document_id=request.document_id,
            matric_no=request.matric_no,
            admin_staff_id=request.admin_staff_id or "ADMIN"
        )
        return PurgeDocumentResponse(**res)
    except PermissionError as pe:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(pe)
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Purge operation failed: {str(e)}"
        )


@router.post(
    "/reject-document",
    response_model=RejectDocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject uploaded document with service-role privileges"
)
async def reject_document(
    request: RejectDocumentRequest,
    jwt_payload: dict = Depends(verify_advisor_jwt),
):
    """
    Advisor Document Rejection:
    Updates uploaded_documents table status to 'Rejected' using service-role privileges,
    bypassing client-side RLS restrictions.
    """
    advisor_id = _extract_advisor_id(jwt_payload)
    if not request.document_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_id is required."
        )
    # Only the student's own advisor (same tenant) may reject this document
    _load_authorized_document(jwt_payload, document_id=request.document_id, allow_student=False)

    try:
        if supabase_svc.client:
            update_payload = {
                "processing_status": "Rejected"
            }
            supabase_svc.client.table("uploaded_documents").update(update_payload).eq("id", request.document_id).execute()
            print(f"[Document Rejection] Document {request.document_id} marked as Rejected by {advisor_id}.")
        return RejectDocumentResponse(
            success=True,
            document_id=request.document_id,
            processing_status="Rejected",
            message=f"Document '{request.document_id}' successfully marked as Rejected."
        )
    except Exception as e:
        print(f"[Document Rejection Error] {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject document: {str(e)}"
        )


@router.post(
    "/submit-verification",
    status_code=status.HTTP_200_OK,
    summary="Student confirms extracted results; server computes any changes and sends to advisor",
)
async def submit_student_verification(
    request: SubmitVerificationRequest,
    jwt_payload: dict = Depends(verify_advisor_jwt),
):
    """
    The student may correct course codes/grades the parser misread, but the
    comparison against the original extraction is done HERE, against the
    server-stored copy. Client-supplied flags (is_altered, ai_grade, fraud_flag)
    are ignored, so a student cannot hide changes from the advisor.
    """
    doc, _role = _load_authorized_document(jwt_payload, document_id=request.document_id, allow_advisor=False)

    if doc.get("processing_status") != "Pending_Student_Verification":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document is not awaiting student verification (status: {doc.get('processing_status')})",
        )

    original = doc.get("extracted_data") or {}
    orig_courses = original.get("original_courses") or original.get("courses") or []
    if not orig_courses:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No extracted data to verify")
    if len(request.courses) != len(orig_courses):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Course list must match the extracted rows (same count and order)",
        )

    merged = []
    for orig, sub in zip(orig_courses, request.courses):
        o_code = str(orig.get("course_code") or "").replace(" ", "").upper()
        o_grade = str(orig.get("grade") or "").strip().upper()
        s_code = str(sub.get("course_code") or o_code).replace(" ", "").upper()
        s_grade = str(sub.get("grade") or o_grade).strip().upper()

        row = {k: v for k, v in orig.items() if k not in ("is_altered", "ai_grade", "ai_course_code")}
        altered = False
        if s_code != o_code:
            row["ai_course_code"] = orig.get("course_code")
            row["course_code"] = s_code
            altered = True
        if s_grade != o_grade:
            row["ai_grade"] = orig.get("grade")
            row["grade"] = s_grade
            altered = True
        row["is_altered"] = altered
        merged.append(row)

    altered_count = sum(1 for r in merged if r["is_altered"])
    new_data = dict(original)
    new_data["original_courses"] = orig_courses
    new_data["courses"] = merged
    new_data["student_altered_count"] = altered_count

    try:
        supabase_svc.client.table("uploaded_documents").update({
            "extracted_data": new_data,
            "processing_status": "Pending_Advisor_Approval",
        }).eq("id", doc["id"]).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit verification: {e}",
        )

    return {"success": True, "document_id": doc["id"], "altered_count": altered_count}


@router.get(
    "/progress/{matric_no}",
    status_code=status.HTTP_200_OK,
    summary="Degree progress check: match academic records against the student's template"
)
async def get_student_progress(
    matric_no: str,
    jwt_payload: dict = Depends(verify_advisor_jwt),
):
    """
    Returns requirement matching progress for a student.

    Authorization:
    - Student: JWT sub must match students.user_id for the given matric_no.
    - Advisor: must be the student's assigned advisor in the same tenant
               (same check as finalize-approval).
    - Anyone else: 403.

    Tenant_id is derived server-side from JWT/DB only, never from the request.

    409 is returned (never silently defaults) when:
    - The student has no cohort assigned.
    - The cohort has no degree template.
    """
    t_start = time.perf_counter()

    jwt_sub = jwt_payload.get("sub")
    if not jwt_sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing sub")
    if not supabase_svc.client:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database client unavailable")

    clean_matric = (matric_no or "").strip().upper()
    if not clean_matric:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="matric_no is required")

    # Stage 1: Load student row & verify authorization
    t_stage1 = time.perf_counter()
    stu_res = (
        supabase_svc.client.table("students")
        .select("matric_no, user_id, advisor_staff_id, tenant_id, cohort_id")
        .eq("matric_no", clean_matric)
        .limit(1)
        .execute()
    )
    if not stu_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student '{clean_matric}' not found")
    student = stu_res.data[0]

    # Authorization: student owns this matric OR is their advisor
    is_student_self = student.get("user_id") == jwt_sub
    is_authorized = is_student_self

    if not is_authorized:
        adv_res = (
            supabase_svc.client.table("advisors")
            .select("staff_id, tenant_id")
            .eq("user_id", jwt_sub)
            .limit(1)
            .execute()
        )
        if (
            adv_res.data
            and adv_res.data[0].get("staff_id") == student.get("advisor_staff_id")
            and adv_res.data[0].get("tenant_id") == student.get("tenant_id")
        ):
            is_authorized = True

    if not is_authorized:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this student's progress")

    tenant_id = student.get("tenant_id") or ""

    # Resolve cohort id (required)
    cohort_id = student.get("cohort_id")
    if not cohort_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Student '{clean_matric}' has no cohort assigned. Assign a cohort before checking progress."
        )

    stage1_ms = (time.perf_counter() - t_stage1) * 1000.0
    logger.info(f"[Progress] {clean_matric} Stage 1 (student & auth): {stage1_ms:.2f}ms")

    # Stage 2: Parallel fetch of independent subsystems
    t_stage2 = time.perf_counter()

    async def _fetch_template_data():
        cohort_res = await _to_thread_retry(
            lambda: supabase_svc.client.table("cohorts")
            .select("template_id")
            .eq("id", cohort_id)
            .limit(1)
            .execute()
        )
        if not cohort_res.data or not cohort_res.data[0].get("template_id"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cohort for student '{clean_matric}' has no degree template assigned."
            )
        template_id = cohort_res.data[0]["template_id"]

        def _fetch_dt():
            return (
                supabase_svc.client.table("degree_templates")
                .select("total_credits_required")
                .eq("id", template_id)
                .limit(1)
                .execute()
            )

        def _fetch_tc():
            return (
                supabase_svc.client.table("template_courses")
                .select("id, course_code, course_name, credit_hour, category, is_elective_slot, slot_no, match_patterns")
                .eq("template_id", template_id)
                .execute()
            )

        dt_res, tc_res = await asyncio.gather(
            _to_thread_retry(_fetch_dt),
            _to_thread_retry(_fetch_tc),
        )

        tmpl_total: Optional[int] = None
        if dt_res.data and dt_res.data[0].get("total_credits_required") is not None:
            try:
                tmpl_total = int(dt_res.data[0]["total_credits_required"])
            except (ValueError, TypeError):
                tmpl_total = None

        template_rows = tc_res.data or []
        if not template_rows:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Degree template '{template_id}' has no courses. Upload a template CSV first."
            )
        return template_rows, tmpl_total

    def _fetch_academic_records():
        rec_res = (
            supabase_svc.client.table("academic_records")
            .select("course_code, course_name, credits, grade, semester, status")
            .eq("tenant_id", tenant_id)
            .eq("matric_no", clean_matric)
            .execute()
        )
        return rec_res.data or []

    def _fetch_repeat_policy():
        return _load_repeat_policy(tenant_id)

    def _fetch_scale():
        try:
            return load_scale(tenant_id, client=supabase_svc.client)
        except ValueError as ve:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No grading scale configured for tenant '{tenant_id}': {ve}"
            )

    def _fetch_overrides():
        ovr_res = (
            supabase_svc.client.table("elective_assignments")
            .select("id, kind, template_course_id, course_code, assigned_by_staff_id, note")
            .eq("tenant_id", tenant_id)
            .eq("matric_no", clean_matric)
            .execute()
        )
        return ovr_res.data or []

    (
        (template_rows, tmpl_total),
        records,
        repeat_policy,
        scale,
        overrides,
    ) = await asyncio.gather(
        _fetch_template_data(),
        _to_thread_retry(_fetch_academic_records),
        _to_thread_retry(_fetch_repeat_policy),
        _to_thread_retry(_fetch_scale),
        _to_thread_retry(_fetch_overrides),
    )

    stage2_ms = (time.perf_counter() - t_stage2) * 1000.0
    logger.info(
        f"[Progress] {clean_matric} Stage 2 (parallel fetch): {stage2_ms:.2f}ms "
        f"(records={len(records)}, overrides={len(overrides)}, template_courses={len(template_rows)})"
    )

    # Stage 3: Progress Engine Computation
    t_stage3 = time.perf_counter()
    try:
        result = compute_progress(
            template_rows=template_rows,
            records=records,
            scale=scale,
            repeat_policy=repeat_policy,
            overrides=overrides,
            template_total_credits=tmpl_total,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Progress computation failed: {e}"
        )

    stage3_ms = (time.perf_counter() - t_stage3) * 1000.0
    total_ms = (time.perf_counter() - t_start) * 1000.0
    logger.info(f"[Progress] {clean_matric} Stage 3 (compute_progress): {stage3_ms:.2f}ms | Total: {total_ms:.2f}ms")

    return {"matric_no": clean_matric, **result}



@router.put("/progress/{matric_no}/overrides", status_code=status.HTTP_200_OK)
async def put_progress_override(
    matric_no: str,
    payload: ElectiveOverrideRequest,
    jwt_payload: Dict[str, Any] = Depends(verify_advisor_jwt),
):
    """
    Advisor only. Set an elective slot override (kind='assign') or course exclusion (kind='exclude').
    Identical advisee authorization as /audit/progress.
    tenant_id and assigned_by_staff_id come from JWT/DB, never request body.
    """
    jwt_sub = jwt_payload.get("sub")
    if not jwt_sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing sub")
    if not supabase_svc.client:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database client unavailable")

    clean_matric = (matric_no or "").strip().upper()
    if not clean_matric:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="matric_no is required")

    # Load student row
    stu_res = (
        supabase_svc.client.table("students")
        .select("matric_no, user_id, advisor_staff_id, tenant_id, cohort_id")
        .eq("matric_no", clean_matric)
        .limit(1)
        .execute()
    )
    if not stu_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student '{clean_matric}' not found")
    student = stu_res.data[0]

    # Advisor only: must match student's assigned advisor
    adv_res = (
        supabase_svc.client.table("advisors")
        .select("staff_id, tenant_id")
        .eq("user_id", jwt_sub)
        .limit(1)
        .execute()
    )
    if (
        not adv_res.data
        or adv_res.data[0].get("staff_id") != student.get("advisor_staff_id")
        or adv_res.data[0].get("tenant_id") != student.get("tenant_id")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the student's assigned advisor can manage progress overrides"
        )
    advisor = adv_res.data[0]
    advisor_staff_id = advisor.get("staff_id")
    tenant_id = advisor.get("tenant_id") or student.get("tenant_id")

    # Validate kind
    kind = (payload.kind or "").strip().lower()
    if kind not in ("assign", "exclude"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="kind must be either 'assign' or 'exclude'"
        )

    clean_course_code = (payload.course_code or "").replace(" ", "").upper()
    if not clean_course_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="course_code is required"
        )

    # 1. Validate that course_code is a counted, passing attempt of this student (grade scale + repeat policy)
    rec_res = (
        supabase_svc.client.table("academic_records")
        .select("course_code, course_name, credits, grade, semester, status")
        .eq("tenant_id", tenant_id)
        .eq("matric_no", clean_matric)
        .execute()
    )
    records = rec_res.data or []
    repeat_policy = _load_repeat_policy(tenant_id)
    try:
        scale = load_scale(tenant_id, client=supabase_svc.client)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No grading scale configured for tenant '{tenant_id}': {ve}"
        )

    counted_attempts = select_attempts_by_repeat_policy(records, scale, repeat_policy)
    matched_attempt = None
    for att in counted_attempts:
        if str(att.get("course_code") or "").replace(" ", "").upper() == clean_course_code:
            matched_attempt = att
            break

    if not matched_attempt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Course '{clean_course_code}' is not a counted attempt for student '{clean_matric}'"
        )

    grade = str(matched_attempt.get("grade") or "").strip().upper()
    if not grade or not scale.counts_as_completed(grade, clean_course_code):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Course '{clean_course_code}' is not a passing attempt (grade: '{grade}')"
        )

    # Resolve student's cohort template
    cohort_id = student.get("cohort_id")
    if not cohort_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Student '{clean_matric}' has no cohort assigned"
        )
    cohort_res = (
        supabase_svc.client.table("cohorts")
        .select("template_id")
        .eq("id", cohort_id)
        .limit(1)
        .execute()
    )
    if not cohort_res.data or not cohort_res.data[0].get("template_id"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cohort for student '{clean_matric}' has no degree template assigned"
        )
    student_template_id = cohort_res.data[0]["template_id"]

    clean_template_course_id = None
    if kind == "assign":
        if not payload.template_course_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="template_course_id is required when kind='assign'"
            )
        clean_template_course_id = str(payload.template_course_id).strip()

        # 2. Validate template_course_id belongs to student's cohort template AND is_elective_slot = true
        tc_res = (
            supabase_svc.client.table("template_courses")
            .select("id, template_id, course_code, is_elective_slot")
            .eq("id", clean_template_course_id)
            .limit(1)
            .execute()
        )
        if not tc_res.data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Template course '{clean_template_course_id}' not found"
            )
        target_tc = tc_res.data[0]
        if str(target_tc.get("template_id")) != str(student_template_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Template course '{clean_template_course_id}' does not belong to student's cohort template"
            )
        if not target_tc.get("is_elective_slot"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Template course '{clean_template_course_id}' is not an elective slot"
            )

        # 3. Validate course_code must not be a core row in the template
        core_res = (
            supabase_svc.client.table("template_courses")
            .select("id")
            .eq("template_id", student_template_id)
            .eq("course_code", clean_course_code)
            .eq("is_elective_slot", False)
            .limit(1)
            .execute()
        )
        if core_res.data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Course '{clean_course_code}' is a core requirement in the template and cannot be assigned to an elective slot"
            )

    # 4. Upsert on (tenant_id, matric_no, course_code).
    # If the target slot already has another assign, replace it.
    if kind == "assign" and clean_template_course_id:
        (
            supabase_svc.client.table("elective_assignments")
            .delete()
            .eq("tenant_id", tenant_id)
            .eq("matric_no", clean_matric)
            .eq("template_course_id", clean_template_course_id)
            .execute()
        )

    # Remove any existing override for this course_code
    (
        supabase_svc.client.table("elective_assignments")
        .delete()
        .eq("tenant_id", tenant_id)
        .eq("matric_no", clean_matric)
        .eq("course_code", clean_course_code)
        .execute()
    )

    insert_data = {
        "tenant_id": tenant_id,
        "matric_no": clean_matric,
        "kind": kind,
        "template_course_id": clean_template_course_id if kind == "assign" else None,
        "course_code": clean_course_code,
        "assigned_by_staff_id": advisor_staff_id,
        "note": (payload.note or "").strip() or None,
    }
    ins_res = (
        supabase_svc.client.table("elective_assignments")
        .insert(insert_data)
        .execute()
    )
    saved_override = ins_res.data[0] if (ins_res.data and len(ins_res.data) > 0) else insert_data
    return {"status": "success", "override": saved_override}


@router.delete("/progress/{matric_no}/overrides/{course_code}", status_code=status.HTTP_200_OK)
async def delete_progress_override(
    matric_no: str,
    course_code: str,
    jwt_payload: Dict[str, Any] = Depends(verify_advisor_jwt),
):
    """
    Advisor only. Remove override for course_code (back to auto-matching).
    Identical advisee authorization as /audit/progress.
    """
    jwt_sub = jwt_payload.get("sub")
    if not jwt_sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing sub")
    if not supabase_svc.client:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database client unavailable")

    clean_matric = (matric_no or "").strip().upper()
    clean_course_code = (course_code or "").replace(" ", "").upper()
    if not clean_matric or not clean_course_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="matric_no and course_code are required")

    # Load student row
    stu_res = (
        supabase_svc.client.table("students")
        .select("matric_no, user_id, advisor_staff_id, tenant_id")
        .eq("matric_no", clean_matric)
        .limit(1)
        .execute()
    )
    if not stu_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student '{clean_matric}' not found")
    student = stu_res.data[0]

    # Advisor only: must match student's assigned advisor
    adv_res = (
        supabase_svc.client.table("advisors")
        .select("staff_id, tenant_id")
        .eq("user_id", jwt_sub)
        .limit(1)
        .execute()
    )
    if (
        not adv_res.data
        or adv_res.data[0].get("staff_id") != student.get("advisor_staff_id")
        or adv_res.data[0].get("tenant_id") != student.get("tenant_id")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the student's assigned advisor can manage progress overrides"
        )
    advisor = adv_res.data[0]
    tenant_id = advisor.get("tenant_id") or student.get("tenant_id")

    (
        supabase_svc.client.table("elective_assignments")
        .delete()
        .eq("tenant_id", tenant_id)
        .eq("matric_no", clean_matric)
        .eq("course_code", clean_course_code)
        .execute()
    )
    return {"status": "success", "message": f"Override for '{clean_course_code}' removed"}
