"""
SynGrad - Slip Lab Endpoint (Staging-Only Diagnostic & Testing Sandbox)
Allows authorized staff/advisors to test transcript slip extraction across rules,
universal AI, and scanned PyMuPDF vision without persisting any documents or DB rows.
Access restricted: ENVIRONMENT must be 'staging' and user email must be in LAB_ALLOWED_EMAILS.
"""

import time
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status

try:
    from app.core.config import settings
    from app.core.auth import _decode_token
    from app.v1.endpoints import audit
except ImportError:
    from backend.app.core.config import settings
    from backend.app.core.auth import _decode_token
    from backend.app.v1.endpoints import audit

logger = logging.getLogger("syngrad.slip_lab")

router = APIRouter(prefix="/lab", tags=["Slip Lab"])


async def verify_lab_access(authorization: Optional[str] = Header(None)) -> dict:
    """
    Enforces access rules:
    1. settings.ENVIRONMENT == "staging" -> otherwise 404
    2. Bearer JWT required and verified
    3. User email must be present in settings.LAB_ALLOWED_EMAILS -> otherwise 403
    """
    if settings.ENVIRONMENT != "staging":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Slip Lab is only available in staging environment.",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header.",
        )

    token = authorization[len("Bearer "):]
    payload = _decode_token(token)
    email = (payload.get("email") or "").strip().lower()

    allowed_list = [
        e.strip().lower() for e in settings.LAB_ALLOWED_EMAILS.split(",") if e.strip()
    ]
    if not email or email not in allowed_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: email not permitted for Slip Lab.",
        )

    return payload


@router.post(
    "/extract",
    summary="Slip Lab extraction test endpoint (staging-only, zero persistence)",
)
async def lab_extract(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    jwt_payload: dict = Depends(verify_lab_access),
) -> Dict[str, Any]:
    """
    Staging-only diagnostic transcript extractor:
    - Runs the exact same extraction pipeline (rules / ai / ai_scan + guardrails + IC redaction).
    - Returns JSON: source, model, semesters, courses, warnings, needs_review, timing.
    - NOTHING is saved: no storage upload, no DB rows.
    """
    if settings.ENVIRONMENT != "staging":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Slip Lab is only available in staging environment.",
        )

    email = (jwt_payload.get("email") or "").strip().lower()
    allowed_list = [
        e.strip().lower() for e in settings.LAB_ALLOWED_EMAILS.split(",") if e.strip()
    ]
    if not email or email not in allowed_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: email not permitted for Slip Lab.",
        )

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded PDF file is empty.",
        )

    slip_profile = audit._load_tenant_slip_profile(tenant_id)
    t0 = time.perf_counter()

    result = audit.run_slip_extraction(
        pdf_bytes=pdf_bytes,
        tenant_id=tenant_id,
        slip_profile=slip_profile,
        expected_matric=None,
        client=audit.supabase_svc.client,
    )

    elapsed = round(time.perf_counter() - t0, 3)

    return {
        "source": result["source"],
        "model": result["model"],
        "semesters": result["semesters"],
        "courses": result["courses"],
        "warnings": result["warnings"],
        "needs_review": result["needs_review"],
        "timing": elapsed,
        "matric_number": result.get("matric_number"),
        "student_name": result.get("student_name"),
        "fraud_flag": result.get("fraud_flag"),
        "gpa": result.get("gpa"),
        "cgpa": result.get("cgpa"),
    }
