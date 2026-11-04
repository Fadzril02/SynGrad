"""
Smart Academic Assessment System - Advising Logs Notification Endpoints
"""

import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel

try:
    from app.core.config import settings
    from app.core.auth import verify_advisor_jwt
    from app.core.supabase_client import SupabaseService
except ImportError:
    from backend.app.core.config import settings
    from backend.app.core.auth import verify_advisor_jwt
    from backend.app.core.supabase_client import SupabaseService

router = APIRouter(prefix="/advising-logs", tags=["Advising Logs"])


class NotifyResponse(BaseModel):
    sent: bool
    reason: Optional[str] = None
    notified_at: Optional[str] = None


@router.post(
    "/{log_id}/notify",
    response_model=NotifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Send student email notification for a shared advising log"
)
async def notify_student_advising_log(
    log_id: str,
    jwt_payload: dict = Depends(verify_advisor_jwt),
):
    """
    Notifies a student by email when a shared advising log is published.

    Rules:
      1. Load log using privileged service role.
      2. 403 Forbidden unless log.advisor_staff_id belongs to the JWT user.
      3. 400 Bad Request if visibility != 'shared'.
      4. 409 Conflict if already notified (notified_at is not null).
      5. Rate limit: skip (return {sent: false, reason: 'rate_limited'}) if the
         student got a notification in the last 60 minutes.
      6. Send via Resend HTTP API using RESEND_API_KEY and RESEND_FROM.
         If either is missing -> 500 fail loud.
      7. PDPA compliant email body with no sensitive note/action item text.
      8. On success, record notified_at = now().
    """
    svc = SupabaseService()
    if not svc.client:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database service client is unavailable.",
        )

    # 1. Load the advising log with the service role
    log_res = (
        svc.client.table("advising_logs")
        .select("*")
        .eq("id", log_id)
        .limit(1)
        .execute()
    )
    if not log_res.data or len(log_res.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Advising log '{log_id}' not found.",
        )
    log = log_res.data[0]

    # 2. Verify advisor ownership: 403 unless log.advisor_staff_id belongs to JWT user
    log_advisor_staff_id = log.get("advisor_staff_id")
    jwt_sub = jwt_payload.get("sub")
    jwt_email = jwt_payload.get("email")
    app_metadata = jwt_payload.get("app_metadata") or {}
    token_staff_id = app_metadata.get("staff_id") or app_metadata.get("advisor_id")

    is_owner = False
    if token_staff_id and token_staff_id == log_advisor_staff_id:
        is_owner = True
    elif jwt_sub or jwt_email:
        try:
            adv_match = (
                svc.client.table("advisors")
                .select("staff_id")
                .eq("staff_id", log_advisor_staff_id)
                .or_(f"user_id.eq.{jwt_sub},institutional_email.eq.{jwt_email}")
                .execute()
            )
            if adv_match.data and len(adv_match.data) > 0:
                is_owner = True
        except Exception as e:
            print(f"[Notify] Advisor ownership lookup error: {e}")

    if not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Advisor does not own advising log '{log_id}'.",
        )

    # 3. Visibility check: 400 if visibility != 'shared'
    if log.get("visibility") != "shared":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot notify student: advising log visibility is not 'shared'.",
        )

    # 4. Conflict check: 409 if already notified
    if log.get("notified_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Advising log has already been notified.",
        )

    # 5. Rate limit check: skip if student received notification email in last 60 minutes
    student_matric = log.get("student_matric_no")
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    try:
        recent_res = (
            svc.client.table("advising_logs")
            .select("id, notified_at")
            .eq("tenant_id", log.get("tenant_id"))
            .eq("student_matric_no", student_matric)
            .neq("id", log_id)
            .gte("notified_at", cutoff)
            .limit(1)
            .execute()
        )
        if recent_res.data and len(recent_res.data) > 0:
            return NotifyResponse(sent=False, reason="rate_limited")
    except Exception as e:
        print(f"[Notify] Rate limit query exception: {e}")

    # 6. Check environment variables: fail loud with 500 if either missing
    resend_api_key = os.getenv("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", None)
    resend_from = os.getenv("RESEND_FROM") or getattr(settings, "RESEND_FROM", None)

    if not resend_api_key or not str(resend_api_key).strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Missing RESEND_API_KEY environment variable. Halting notification to fail loud.",
        )
    if not resend_from or not str(resend_from).strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Missing RESEND_FROM environment variable. Halting notification to fail loud.",
        )

    # 7. Look up student recipient email and student & advisor names
    student_res = (
        svc.client.table("students")
        .select("name, institutional_email")
        .eq("tenant_id", log.get("tenant_id"))
        .eq("matric_no", student_matric)
        .limit(1)
        .execute()
    )
    student_name = "Student"
    student_email = None
    if student_res.data and len(student_res.data) > 0:
        st_row = student_res.data[0]
        student_name = st_row.get("name") or "Student"
        student_email = st_row.get("institutional_email")

    if not student_email or not str(student_email).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Student '{student_matric}' has no institutional email address on file.",
        )

    advisor_name = "Advisor"
    try:
        adv_name_res = (
            svc.client.table("advisors")
            .select("name")
            .eq("staff_id", log_advisor_staff_id)
            .limit(1)
            .execute()
        )
        if adv_name_res.data and len(adv_name_res.data) > 0:
            advisor_name = adv_name_res.data[0].get("name") or "Advisor"
    except Exception as e:
        print(f"[Notify] Advisor name lookup error: {e}")

    # 8. Email body: PDPA compliant — do NOT include note text or action item
    email_body = f"Hi {student_name}, your advisor {advisor_name} shared a new advising note on SynGrad. Log in to view it: https://syngrad.my"

    resend_payload = {
        "from": resend_from.strip(),
        "to": [student_email.strip()],
        "subject": "New advising note on SynGrad",
        "text": email_body,
    }

    # 9. Send via Resend HTTP API
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            resend_resp = await http_client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_api_key.strip()}",
                    "Content-Type": "application/json",
                },
                json=resend_payload,
            )
            if resend_resp.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Resend HTTP API returned error {resend_resp.status_code}: {resend_resp.text}",
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to communicate with Resend API: {str(exc)}",
        )

    # 10. Record notified_at = now()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        svc.client.table("advising_logs").update({"notified_at": now_iso}).eq("id", log_id).execute()
    except Exception as e:
        print(f"[Notify] Failed to record notified_at on log '{log_id}': {e}")

    return NotifyResponse(sent=True, notified_at=now_iso)
