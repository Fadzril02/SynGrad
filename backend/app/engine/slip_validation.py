"""
SynGrad - Slip Validation Guardrails Module (Pure Functions)
Validates parsed academic slip data (rules and AI) against strict institutional rules.
Never changes values; returns (warnings, needs_review).
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from app.engine.grading import GradingScale, normalize_semester
except ImportError:
    from backend.app.engine.grading import GradingScale, normalize_semester


COURSE_CODE_PATTERN = re.compile(r'^[A-Z0-9\-_]{2,15}$', re.IGNORECASE)


def validate_course_code(code: str) -> Optional[str]:
    """Returns a warning string if course code format is not sane, else None."""
    if not code or not str(code).strip():
        return "Missing course code"
    clean_code = str(code).replace(" ", "").upper()
    if not COURSE_CODE_PATTERN.match(clean_code):
        return f"Unusual course code format: '{code}'"
    return None


def validate_credits(credits_val: Any, course_code: str = "") -> Optional[str]:
    """
    Validates credit hours.
    Allows decimals in validation; if not whole, flags warning "decimal credits not supported yet".
    If credits <= 0, flags warning.
    """
    if credits_val is None:
        return f"Missing credits for course '{course_code}'" if course_code else "Missing credits"
    try:
        val = float(credits_val)
    except (ValueError, TypeError):
        return f"Invalid credits value '{credits_val}' for course '{course_code}'"

    if val <= 0:
        return f"Credits must be greater than 0 (got {credits_val}) for course '{course_code}'"

    if not val.is_integer():
        return f"Decimal credits ({credits_val}) for course '{course_code}' not supported yet"

    return None


def validate_grade(grade: str, scale: GradingScale, course_code: str = "") -> Optional[str]:
    """Validates that grade exists in the tenant's grading scale."""
    if not grade or not str(grade).strip():
        return f"Missing grade for course '{course_code}'"
    clean_grade = str(grade).strip().upper()
    if clean_grade not in scale._by_grade:
        return f"Unknown grade '{clean_grade}' for course '{course_code}' in tenant grading scale"
    return None


def validate_semester_session(sem_no: Any, session: Any) -> Optional[str]:
    """Validates that semester and session are normalisable via grading.normalize_semester."""
    if sem_no is None and not session:
        return None
    raw_label = f"SEM {sem_no} {session}".strip()
    try:
        normalize_semester(raw_label)
        return None
    except ValueError as e:
        return f"Invalid semester/session format '{raw_label}': {e}"


def check_gpa_mismatch(
    courses: List[Dict[str, Any]],
    printed_gpa: Optional[float],
    scale: GradingScale
) -> Optional[str]:
    """
    Recomputes semester GPA using tenant grading scale and compares against printed GPA.
    Tolerance is 0.01. Returns warning string on mismatch.
    """
    if printed_gpa is None:
        return None

    tot_pts = 0.0
    tot_credits = 0.0

    for c in courses:
        g = str(c.get("grade") or "").strip().upper()
        code = str(c.get("code") or c.get("course_code") or "").strip().upper()
        if not g or g not in scale._by_grade:
            continue
        try:
            if scale.counts_in_cgpa(g, code):
                gp = scale.grade_points(g, code)
                raw_cr = c.get("credits") or c.get("credit_hour") or 0
                cr = float(raw_cr)
                tot_pts += (gp * cr)
                tot_credits += cr
        except Exception:
            continue

    if tot_credits > 0:
        computed_gpa = round(tot_pts / tot_credits, 2)
        if abs(computed_gpa - float(printed_gpa)) > 0.01:
            return f"GPA mismatch with transcript (computed {computed_gpa:.2f} vs printed {float(printed_gpa):.2f})"

    return None


def validate_slip(
    slip_data: Dict[str, Any],
    scale: GradingScale,
    expected_matric: Optional[str] = None
) -> Tuple[List[str], bool]:
    """
    Pure guardrail validation applied to BOTH rule and AI outputs.
    Checks:
    - grade must exist in tenant grade scale
    - credits > 0 (decimals flagged as not supported yet)
    - course code format sane
    - semester/session normalisable via normalize_semester
    - recomputed GPA vs printed GPA (0.01 tolerance)
    - slip matric != expected_matric -> blocking warning "This slip may belong to someone else"

    Returns (warnings, needs_review).
    Never mutates values.
    """
    warnings: List[str] = []

    # 1. Matric Check (blocking warning if mismatched)
    slip_matric = slip_data.get("matric_no") or slip_data.get("matric_number")
    if slip_matric and expected_matric:
        c_slip = str(slip_matric).strip().upper()
        c_exp = str(expected_matric).strip().upper()
        if c_slip != c_exp:
            warnings.append("This slip may belong to someone else")

    # 2. Extract semesters or construct single semester view
    semesters = slip_data.get("semesters")
    if not semesters:
        # Fallback to top-level courses list
        courses = slip_data.get("courses") or []
        sem_no = slip_data.get("semester")
        sess = slip_data.get("academic_session")
        printed_gpa = slip_data.get("png") or slip_data.get("gpa")
        semesters = [{
            "semester_no": sem_no,
            "session": sess,
            "courses": courses,
            "printed_gpa": printed_gpa,
        }]

    # 3. Validate each semester
    for sem in semesters:
        if not isinstance(sem, dict):
            continue

        sem_no = sem.get("semester_no")
        session = sem.get("session")
        if sem_no is not None or session:
            sem_warn = validate_semester_session(sem_no, session)
            if sem_warn and sem_warn not in warnings:
                warnings.append(sem_warn)

        sem_courses = sem.get("courses") or []
        for c in sem_courses:
            if not isinstance(c, dict):
                continue
            code = str(c.get("code") or c.get("course_code") or "").strip()
            grade = str(c.get("grade") or "").strip()
            creds = c.get("credits") or c.get("credit_hour")

            # Check course code
            c_code_warn = validate_course_code(code)
            if c_code_warn and c_code_warn not in warnings:
                warnings.append(c_code_warn)

            # Check credits
            cr_warn = validate_credits(creds, code)
            if cr_warn and cr_warn not in warnings:
                warnings.append(cr_warn)

            # Check grade
            g_warn = validate_grade(grade, scale, code)
            if g_warn and g_warn not in warnings:
                warnings.append(g_warn)

            # Check per-course session_semester if present
            item_sem = c.get("session_semester")
            if item_sem:
                try:
                    normalize_semester(item_sem)
                except ValueError as ve:
                    item_sem_warn = f"Cannot normalise semester label '{item_sem}' for course '{code}': {ve}"
                    if item_sem_warn not in warnings:
                        warnings.append(item_sem_warn)

        # Check GPA mismatch
        printed_gpa = sem.get("printed_gpa")
        gpa_warn = check_gpa_mismatch(sem_courses, printed_gpa, scale)
        if gpa_warn and gpa_warn not in warnings:
            warnings.append(gpa_warn)

    needs_review = len(warnings) > 0
    return warnings, needs_review
