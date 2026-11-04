"""
Smart Academic Assessment System - Supabase Service & Client Integration
"""

from typing import Dict, Any, List, Optional
from supabase import create_client, Client
try:
    from app.core.config import settings
    from app.schemas.audit import CourseAuditResult, AuditSummary
    from app.engine.grading import normalize_semester
except ImportError:
    from backend.app.core.config import settings
    from backend.app.schemas.audit import CourseAuditResult, AuditSummary
    from backend.app.engine.grading import normalize_semester


def get_supabase_client() -> Optional[Client]:
    """
    Creates and returns a Supabase client instance using Service Role Key.
    Refuses to silently fall back to Anon Key. Fails loudly with detailed diagnostics.
    """
    url = (settings.SUPABASE_URL or "").strip()
    sr_key = (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()
    anon_key = (settings.SUPABASE_ANON_KEY or "").strip()

    if not url:
        raise RuntimeError("CRITICAL: SUPABASE_URL is missing or empty in backend environment.")

    if not sr_key:
        raise RuntimeError(
            "CRITICAL: SUPABASE_SERVICE_ROLE_KEY is missing or empty in backend environment. "
            "Backend strictly requires privileged service_role credentials to bypass RLS and execute audits."
        )

    if anon_key and sr_key == anon_key:
        raise RuntimeError(
            "CRITICAL: SUPABASE_SERVICE_ROLE_KEY is identical to SUPABASE_ANON_KEY. "
            "The anon key cannot bypass RLS for administrative operations. Supply the real service_role key."
        )

    # Force HTTP/1.1 with a connection pool. The default shared HTTP/2 connection gets
    # dropped (GOAWAY / "ConnectionTerminated" / "Server disconnected") when several
    # threads query in parallel (e.g. /audit/progress). HTTP/1.1 pools are thread-safe.
    import httpx
    from supabase.lib.client_options import SyncClientOptions
    http_client = httpx.Client(
        http2=False,
        timeout=httpx.Timeout(30.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
    # Requires supabase>=2.31 (httpx_client option). No silent fallback to the shared HTTP/2 client.
    return create_client(url, sr_key, options=SyncClientOptions(httpx_client=http_client))


class SupabaseService:
    def __init__(self):
        self.init_error: Optional[str] = None
        try:
            self.client: Optional[Client] = get_supabase_client()
        except RuntimeError as err:
            self.client = None
            self.init_error = str(err)
            print(f"[FATAL CONFIGURATION ERROR] {err}", flush=True)

    def _ensure_ready(self):
        if not self.client:
            raise RuntimeError(
                f"FATAL BACKEND CONFIGURATION ERROR: Supabase Service Role client is uninitialized: {self.init_error}"
            )

    def download_transcript_bytes(self, storage_path: str) -> bytes:
        """
        Downloads PDF bytes from private 'transcripts' / 'academic-slips' bucket using Service Role privileges.
        """
        self._ensure_ready()
        
        # storage_path may be 'transcripts/advisor_id/filename.pdf' or 'academic-slips/filename.pdf'
        clean_path = storage_path.removeprefix("transcripts/").removeprefix("academic-slips/").removeprefix("/")
        bucket = "academic-slips" if "academic-slips" in storage_path else "transcripts"
        
        try:
            res = self.client.storage.from_(bucket).download(clean_path)
            return res
        except Exception:
            # Fallback to alternative bucket if default not found
            fallback_bucket = "transcripts" if bucket == "academic-slips" else "academic-slips"
            return self.client.storage.from_(fallback_bucket).download(clean_path)

    def delete_file_from_storage(self, bucket_name: str, file_path: str) -> bool:
        """
        Auto-Purge: Deletes a file from Supabase Storage after extraction is complete.

        Called immediately after PyMuPDF extracts text from the PDF bytes, so the raw
        PDF is never retained beyond the extraction step. This keeps the Supabase free-tier
        storage bucket from accumulating uploaded transcripts indefinitely.

        Args:
            bucket_name: The storage bucket ('academic-slips' or 'transcripts').
            file_path:   The clean relative file path within the bucket.

        Returns:
            True  — file was successfully removed from storage.
            False — removal failed (file not found, permissions, etc.).
                    A warning is logged but the exception is NOT re-raised so the
                    caller's response pipeline is never interrupted.
        """
        if not self.client:
            print(f"[delete_file_from_storage] Client not ready — skipping purge of '{file_path}'.")
            return False
        try:
            clean_path = (
                file_path
                .removeprefix("transcripts/")
                .removeprefix("academic-slips/")
                .removeprefix("/")
            )
            removed = self.client.storage.from_(bucket_name).remove([clean_path])
            if not removed:
                # Storage returns the list of deleted objects; empty = nothing was deleted (wrong bucket/path).
                print(f"[Auto-Purge ERROR] Nothing deleted for '{clean_path}' in bucket '{bucket_name}' — file may still exist (PDPA).")
                return False
            print(f"[Auto-Purge] Deleted '{clean_path}' from bucket '{bucket_name}'.")
            return True
        except Exception as e:
            print(f"[Auto-Purge WARNING] Could not delete '{file_path}' from '{bucket_name}': {e}")
            return False

    def _student_template_id(self, matric_no: str, tenant_id: str) -> Optional[str]:
        """student -> cohort -> template_id, scoped to the tenant. None when no cohort/template. DB errors raise."""
        self._ensure_ready()
        if not tenant_id:
            raise ValueError("tenant_id is required to resolve a student's degree template.")
        stu = (
            self.client.table("students").select("cohort_id")
            .eq("tenant_id", tenant_id).eq("matric_no", (matric_no or "").strip().upper())
            .limit(1).execute()
        )
        cohort_id = stu.data[0].get("cohort_id") if stu.data else None
        if not cohort_id:
            return None
        cohort = self.client.table("cohorts").select("template_id").eq("id", cohort_id).limit(1).execute()
        return cohort.data[0].get("template_id") if cohort.data else None

    def get_template_course_catalog(
        self, matric_no: str, tenant_id: str
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        Course catalogue (code -> {code, name, credits, category, prerequisites}) from the
        student's degree template: student -> cohort -> template -> template_courses.
        Returns None when the student has no cohort/template yet. DB errors raise.
        """
        template_id = self._student_template_id(matric_no, tenant_id)
        if not template_id:
            return None

        rows = (
            self.client.table("template_courses")
            .select("course_code, course_name, credit_hour, category, prerequisites")
            .eq("template_id", template_id).execute()
        )
        catalog: Dict[str, Dict[str, Any]] = {}
        for row in rows.data or []:
            code = (row.get("course_code") or "").replace(" ", "").upper()
            if code:
                catalog[code] = {
                    "code": code,
                    "name": row.get("course_name") or "",
                    "credits": row.get("credit_hour"),
                    "category": row.get("category") or "",
                    "prerequisites": row.get("prerequisites") or {},
                }
        return catalog

    def get_or_create_student(
        self,
        university_id: str,
        advisor_id: str,
        matric_number: str,
        student_name: str,
        curriculum_year: Optional[str] = None,
        program_code: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Finds existing student or inserts a new student record into 'students' table.
        """
        clean_matric = (matric_number or "").strip().upper()
        if not clean_matric:
            raise ValueError("Student matric_number is required.")

        clean_advisor = (advisor_id or "").strip()
        if not clean_advisor:
            raise ValueError("advisor_id is required to create a student record.")

        if not self.client:
            return {"matric_no": clean_matric, "name": student_name}

        if not tenant_id:
            raise ValueError("tenant_id is required to find or create a student record.")

        # Check existing student by (tenant_id, matric_no)
        res = self.client.table("students").select("*").eq("tenant_id", tenant_id).eq("matric_no", clean_matric).execute()
        if res.data:
            return res.data[0]

        # Insert new student record matching live schema
        new_student = {
            "tenant_id": tenant_id,
            "matric_no": clean_matric,
            "name": student_name,
            "advisor_staff_id": clean_advisor,
            "program": program_code,
            "syllabus_type": curriculum_year,
            "academic_status": "Good Standing"
        }
        ins_res = self.client.table("students").insert(new_student).execute()
        return ins_res.data[0] if ins_res.data else new_student

    def get_student_block_exempted_credits(
        self,
        matric_no: str,
        tenant_id: str
    ) -> tuple[int, Optional[int]]:
        """
        Fetches block_exempted_credits and graduation_credit_requirement from the
        students table for Diploma/Transfer students who enter with pre-approved credits.

        Returns:
            (block_exempted_credits: int, graduation_credit_requirement: int | None)
            (0, None) only when the student row has no values. DB errors raise.
        """
        self._ensure_ready()
        clean_matric = (matric_no or "").strip().upper()
        if not clean_matric or not tenant_id:
            raise ValueError("matric_no and tenant_id are required to read a student's credit overrides.")
        res = (
            self.client
            .table("students")
            .select("block_exempted_credits, graduation_credit_requirement")
            .eq("tenant_id", tenant_id)
            .eq("matric_no", clean_matric)
            .limit(1)
            .execute()
        )
        if not res.data:
            return 0, None
        block_credits = int(res.data[0].get("block_exempted_credits") or 0)
        grad_req = res.data[0].get("graduation_credit_requirement")
        return block_credits, int(grad_req) if grad_req is not None else None

    def persist_audit_results(
        self,
        matric_no: str,
        advisor_id: str,
        records: List[CourseAuditResult],
        summary: AuditSummary,
        storage_pdf_path: str,
        student_id: Optional[str] = None,
        tenant_id: str = "UTM"
    ) -> str:
        """
        Saves parsed academic records and degree audit snapshot to PostgreSQL.
        Binds matric_no directly from the request string.
        Returns audit_id UUID.
        """
        target_matric = (matric_no or student_id or "").strip()
        if not target_matric or target_matric == "00000000-0000-0000-0000-000000000000":
            raise ValueError("Valid student matric_no is required to persist audit results. Placeholder UUIDs are forbidden.")

        self._ensure_ready()

        try:
            # 1. Dedupe the batch on (course_code, semester), keeping the new/latest record
            deduped_map: Dict[tuple, Any] = {}
            for r in records:
                c_code = r.course_code.replace(" ", "").upper()
                c_sem = normalize_semester(r.semester)
                deduped_map[(c_code, c_sem)] = (r, c_code, c_sem)

            records_to_upsert = [
                {
                    "tenant_id": tenant_id,
                    "matric_no": target_matric,
                    "course_code": c_code,
                    "course_name": r.course_name,
                    "credits": r.credits,
                    "grade": r.grade,
                    "grade_point": r.grade_point,
                    "semester": c_sem,
                    "status": r.status,
                    "prerequisite_met": getattr(r, "prerequisite_met", True),
                    "missing_prerequisites": getattr(r, "missing_prerequisites", []),
                    "is_ai_parsed": getattr(r, "is_ai_parsed", False),
                    "raw_extracted_text": getattr(r, "raw_extracted_text", "")
                }
                for r, c_code, c_sem in deduped_map.values()
            ]
            if records_to_upsert:
                self.client.table("academic_records").upsert(
                    records_to_upsert,
                    on_conflict="tenant_id,matric_no,course_code,semester"
                ).execute()

            # 3. Update student CGPA & Credits
            update_data = {
                "cgpa": summary.cgpa,
                "academic_status": "Good Standing" if summary.overall_traffic_light != "RED" else "At-Risk",
                "audit_status": "Approved"
            }
            self.client.table("students").update(update_data).eq("tenant_id", tenant_id).eq("matric_no", target_matric).execute()

            # 4. Insert degree_audits snapshot
            audit_record = {
                "matric_no": target_matric,
                "advisor_staff_id": advisor_id,
                "audit_status": "COMPLETED",
                "total_credits_required": summary.total_credits_required,
                "total_credits_earned": summary.total_credits_earned,
                "traffic_light_status": summary.overall_traffic_light,
                "unmet_prerequisites_count": summary.unmet_prerequisites_count,
                "failed_courses_count": summary.failed_courses_count,
                "audit_summary": summary.model_dump(),
                "storage_pdf_path": storage_pdf_path
            }
            audit_res = self.client.table("degree_audits").insert(audit_record).execute()
            if not audit_res or not audit_res.data:
                raise RuntimeError("degree_audits insert returned no row")
            return audit_res.data[0]["id"]
        except Exception as e:
            print(f"[Supabase Persistence Warning] {e}")
            raise e

    def purge_uploaded_document_file(
        self,
        document_id: Optional[str] = None,
        matric_no: Optional[str] = None,
        admin_staff_id: Optional[str] = "ADMIN"
    ) -> Dict[str, Any]:
        """
        Securely purges raw transcript PDF from storage while preserving database row & audit trail.
        
        Policy Rules (Pilot / UAT):
        1. Target document MUST have processing_status == 'Approved' (advisor verified).
        2. If status is 'Pending_Student_Verification', 'Pending_Advisor_Approval', or 'Rejected',
           the purge request is aborted to protect audit review capabilities.
        3. Deletes file from the 'academic-slips' bucket.
        4. Only if the delete succeeded: sets file_path = '[PURGED]' (preserves row id, foreign keys, extracted data).
        5. Inserts an immutable entry into system_audit_logs with action_type 'DELETE'.
        
        Note: Automatic purge-on-approval is the intended production behavior for Phase 2.
        """
        self._ensure_ready()

        if not document_id and not matric_no:
            raise ValueError("Must provide either document_id or matric_no to purge.")

        # 1. Fetch document record
        query = self.client.table("uploaded_documents").select("*")
        if document_id:
            query = query.eq("id", document_id)
        elif matric_no:
            query = query.eq("matric_no", matric_no)
        
        doc_res = query.execute()
        if not doc_res.data or len(doc_res.data) == 0:
            raise ValueError(f"No document found matching criteria (id: {document_id}, matric: {matric_no}).")

        target_doc = doc_res.data[0]
        doc_id = target_doc["id"]
        current_status = target_doc.get("processing_status", "")
        file_path = target_doc.get("file_path")

        # 2. Status Enforcement: MUST be 'Approved'
        if current_status != "Approved":
            raise PermissionError(
                f"Cannot purge document '{doc_id}' with status '{current_status}'. "
                "Purge is strictly permitted only after advisor approval ('Approved') to allow audit verification."
            )

        # 3. Check if file is already purged
        if not file_path or file_path in {"", "[PURGED]"}:
            return {
                "success": True,
                "message": f"Document '{doc_id}' file is already purged (file_path is [PURGED]).",
                "document_id": doc_id,
                "file_path": "[PURGED]",
                "processing_status": current_status
            }

        # 4. Delete file from Supabase Storage; keep file_path on failure so the file can still be found (PDPA)
        storage_deleted = self.delete_file_from_storage(bucket_name="academic-slips", file_path=file_path)
        if not storage_deleted:
            print(f"[Auto-Purge ERROR] Document '{doc_id}': '{file_path}' not deleted from storage; file_path kept.")
            return {
                "success": False,
                "message": f"Storage delete failed for document '{doc_id}'; file_path kept.",
                "document_id": doc_id,
                "purged_file_path": None,
                "storage_deleted": False,
                "processing_status": current_status
            }

        # 5. Update database row: mark file_path as [PURGED] (preserves NOT NULL constraint & foreign keys)
        self.client.table("uploaded_documents").update({
            "file_path": "[PURGED]"
        }).eq("id", doc_id).execute()

        # 6. Insert into system_audit_logs
        valid_admin = admin_staff_id if admin_staff_id in {"ADMIN1", "ADMIN-CLI"} else "ADMIN1"
        log_entry = {
            "admin_staff_id": valid_admin,
            "action_type": "DELETE",
            "target_table": "uploaded_documents",
            "record_id": doc_id,
            "description": f"Purged transcript PDF '{file_path}' from storage bucket after advisor approval."
        }
        try:
            self.client.table("system_audit_logs").insert(log_entry).execute()
        except Exception as log_err:
            # Fallback with admin_staff_id = None if FK fails
            try:
                log_entry["admin_staff_id"] = None
                self.client.table("system_audit_logs").insert(log_entry).execute()
            except Exception as log_err2:
                print(f"[Audit Log Warning] Could not write to system_audit_logs: {log_err2}")

        return {
            "success": True,
            "message": f"Successfully purged file for document '{doc_id}'.",
            "document_id": doc_id,
            "purged_file_path": file_path,
            "storage_deleted": storage_deleted,
            "processing_status": current_status
        }

    def get_student_required_credits(self, matric_no: str, tenant_id: str) -> Optional[int]:
        """
        total_credits_required from the student's degree template (student -> cohort -> template).
        Returns None when the student has no cohort/template or the template has no total. DB errors raise.
        """
        template_id = self._student_template_id(matric_no, tenant_id)
        if not template_id:
            return None

        tmpl = (
            self.client.table("degree_templates").select("total_credits_required")
            .eq("id", template_id).limit(1).execute()
        )
        total = tmpl.data[0].get("total_credits_required") if tmpl.data else None
        return int(total) if total is not None else None


