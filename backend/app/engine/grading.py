"""
Smart Academic Assessment System - Per-University Grading Scale Engine
Free-tier safe, fail-loud grading and credit calculation.
Strict multi-tenant: no hardcoded tenant fallbacks.
"""

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Dict, List, Optional, Any, Union

try:
    from app.core.supabase_client import SupabaseService
except ImportError:
    try:
        from backend.app.core.supabase_client import SupabaseService
    except ImportError:
        SupabaseService = None  # type: ignore


@dataclass
class GradeDefinition:
    grade: str
    points: Optional[float]
    rank: Optional[int]
    is_pass: bool
    counts_in_cgpa: bool
    counts_as_completed: bool
    min_mark: Optional[int] = None
    max_mark: Optional[int] = None
    achievement_label: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class GradingScale:
    def __init__(self, tenant_id: str, definitions: List[GradeDefinition]):
        if not definitions:
            raise ValueError(f"GradingScale for tenant '{tenant_id}' cannot be empty.")
        self.tenant_id = tenant_id
        self._by_grade: Dict[str, GradeDefinition] = {
            d.grade.strip().upper(): d for d in definitions
        }

    def get_definition(self, grade: str, course_code: str = "") -> GradeDefinition:
        if not grade:
            raise ValueError(f"Unknown grade '{grade}' for course '{course_code}'")
        clean_g = str(grade).strip().upper()
        if clean_g not in self._by_grade:
            raise ValueError(f"Unknown grade '{grade}' for course '{course_code}'")
        return self._by_grade[clean_g]

    def grade_points(self, grade: str, course_code: str = "") -> float:
        defn = self.get_definition(grade, course_code)
        return float(defn.points) if defn.points is not None else 0.0

    def is_pass(self, grade: str, course_code: str = "") -> bool:
        defn = self.get_definition(grade, course_code)
        return defn.is_pass

    def counts_in_cgpa(self, grade: str, course_code: str = "") -> bool:
        defn = self.get_definition(grade, course_code)
        return defn.counts_in_cgpa

    def counts_as_completed(self, grade: str, course_code: str = "") -> bool:
        defn = self.get_definition(grade, course_code)
        return defn.counts_as_completed

    def meets_min_grade(self, grade: str, min_grade: Optional[str], course_code: str = "") -> bool:
        if not min_grade or str(min_grade).strip().upper() in {"", "NONE", "ANY"}:
            return self.is_pass(grade, course_code)

        # Fails loud with ValueError if grade or min_grade is unknown
        grade_defn = self.get_definition(grade, course_code)
        min_defn = self.get_definition(min_grade, course_code)

        # Special neutral passing grades (e.g. EX, CT, HL, PC) always satisfy prerequisites
        if grade_defn.is_pass and not grade_defn.counts_in_cgpa and grade_defn.counts_as_completed:
            return True

        if not grade_defn.is_pass:
            return False

        # Rank-based comparison: lower numerical rank indicates a higher/better grade (rank 1 <= rank 8)
        if grade_defn.rank is not None and min_defn.rank is not None:
            return grade_defn.rank <= min_defn.rank

        # Fallback to points comparison if ranks are not assigned
        if grade_defn.points is not None and min_defn.points is not None:
            return grade_defn.points >= min_defn.points

        return grade_defn.is_pass


def load_scale(
    tenant_id: str,
    as_of_date: Optional[Union[date, str]] = None,
    client: Optional[Any] = None
) -> GradingScale:
    """
    Loads grading scale from database for the specified tenant effective as of as_of_date.
    Raises ValueError immediately if the tenant has no rows in grade_scales.
    """
    if not tenant_id or not str(tenant_id).strip():
        raise ValueError("tenant_id must be provided to load_scale.")

    as_of: date
    if as_of_date is None:
        as_of = date.today()
    elif isinstance(as_of_date, str):
        try:
            as_of = datetime.strptime(as_of_date, "%Y-%m-%d").date()
        except ValueError:
            as_of = date.today()
    else:
        as_of = as_of_date

    sb_client = client
    if sb_client is None and SupabaseService is not None:
        try:
            svc = SupabaseService()
            sb_client = svc.client
        except Exception as e:
            raise ValueError(f"Database service unavailable: {e}")

    if sb_client is None:
        raise ValueError(f"Cannot load grading scale: database client is unavailable for tenant '{tenant_id}'.")

    try:
        # Case-insensitive / normalized tenant lookup: match exact or uppercase
        import httpx
        def _q():
            return sb_client.table("grade_scales").select("*").or_(f"tenant_id.eq.{tenant_id},tenant_id.eq.{tenant_id.upper()},tenant_id.eq.{tenant_id.lower()}").execute()
        try:
            res = _q()
        except httpx.TransportError:
            # Dropped shared HTTP/2 connection; idempotent read, retry once.
            res = _q()
        rows = res.data if res else []
    except Exception as e:
        raise ValueError(f"Failed to query grade_scales for tenant '{tenant_id}': {e}")

    if not rows:
        raise ValueError(f"No grading scale found for tenant '{tenant_id}'")

    valid_defs: List[GradeDefinition] = []
    for r in rows:
        ef_from_str = r.get("effective_from")
        ef_to_str = r.get("effective_to")
        ef_from = datetime.strptime(ef_from_str, "%Y-%m-%d").date() if ef_from_str else date(1970, 1, 1)
        ef_to = datetime.strptime(ef_to_str, "%Y-%m-%d").date() if ef_to_str else None

        if ef_from <= as_of and (ef_to is None or ef_to >= as_of):
            valid_defs.append(GradeDefinition(
                grade=r["grade"],
                points=float(r["points"]) if r.get("points") is not None else None,
                rank=int(r["rank"]) if r.get("rank") is not None else None,
                min_mark=int(r["min_mark"]) if r.get("min_mark") is not None else None,
                max_mark=int(r["max_mark"]) if r.get("max_mark") is not None else None,
                achievement_label=r.get("achievement_label"),
                is_pass=bool(r["is_pass"]),
                counts_in_cgpa=bool(r["counts_in_cgpa"]),
                counts_as_completed=bool(r["counts_as_completed"]),
                effective_from=ef_from,
                effective_to=ef_to
            ))

    if not valid_defs:
        raise ValueError(f"No active grading scale definitions for tenant '{tenant_id}' as of {as_of}")

    return GradingScale(tenant_id, valid_defs)


# ---------------------------------------------------------------------------
# CGPA & Completed Credits Calculations
# ---------------------------------------------------------------------------
def _parse_semester_sort_key(semester: str, idx: int) -> tuple:
    """
    Produces a chronological sort key for a semester string, falling back to index order.
    Example: 'Sem 1 2021/2022' -> (2021, 1, idx)
             '2021/2022-1'     -> (2021, 1, idx)
    """
    if not semester:
        return (0, 0, idx)
    sem_str = str(semester).strip()
    year_match = re.search(r'(\d{4})', sem_str)
    sem_match = re.search(r'(?:Sem(?:ester)?)\s*[:.]?\s*([1-4])', sem_str, re.IGNORECASE)
    sem_num = 0
    if sem_match:
        sem_num = int(sem_match.group(1))
    else:
        dash_m = re.search(r'[-\/\s]([1-4])$', sem_str)
        if dash_m:
            sem_num = int(dash_m.group(1))

    year = int(year_match.group(1)) if year_match else 0
    return (year, sem_num, idx)


def compute_cgpa(
    records: List[Any],
    scale: GradingScale,
    repeat_policy: str = "latest"
) -> float:
    """
    Computes cumulative GPA across a list of course records according to repeat_policy ('latest' vs 'best').
    Excludes non-CGPA courses (EX, CT, HL, PC, TD, TS).
    Raises ValueError immediately if any course has an unknown grade.
    """
    if not records:
        return 0.00

    # Group attempts by normalized course code
    attempts_by_course: Dict[str, List[tuple]] = {}

    for idx, rec in enumerate(records):
        code = getattr(rec, "course_code", None) if not isinstance(rec, dict) else rec.get("course_code")
        grade = getattr(rec, "grade", None) if not isinstance(rec, dict) else rec.get("grade")
        creds = getattr(rec, "credits", None) if not isinstance(rec, dict) else rec.get("credits")
        sem = getattr(rec, "semester", None) if not isinstance(rec, dict) else rec.get("semester")

        clean_code = str(code or "").replace(" ", "").upper()
        if not clean_code or not grade:
            continue

        if creds is None:
            raise ValueError(f"Missing credits for {code}")
        credits_val = int(creds)

        # Validate grade existence (fail loud)
        defn = scale.get_definition(grade, clean_code)

        if clean_code not in attempts_by_course:
            attempts_by_course[clean_code] = []

        sort_key = _parse_semester_sort_key(str(sem or ""), idx)
        attempts_by_course[clean_code].append((sort_key, grade, credits_val, defn))

    total_grade_points = 0.0
    total_gpa_credits = 0

    for course_code, course_attempts in attempts_by_course.items():
        # Filter for attempts that count in CGPA
        cgpa_attempts = [a for a in course_attempts if a[3].counts_in_cgpa]
        if not cgpa_attempts:
            continue

        selected_attempt: tuple
        if len(cgpa_attempts) == 1:
            selected_attempt = cgpa_attempts[0]
        else:
            if repeat_policy == "best":
                # Maximize points; if points equal, prefer lower rank; then latest semester
                selected_attempt = max(
                    cgpa_attempts,
                    key=lambda a: (
                        a[3].points if a[3].points is not None else 0.0,
                        -(a[3].rank if a[3].rank is not None else 999),
                        a[0]
                    )
                )
            else:  # 'latest'
                # Sort by semester chronology, latest attempt wins
                selected_attempt = max(cgpa_attempts, key=lambda a: a[0])

        _, chosen_grade, chosen_credits, chosen_defn = selected_attempt
        gp = chosen_defn.points if chosen_defn.points is not None else 0.0
        total_grade_points += (gp * chosen_credits)
        total_gpa_credits += chosen_credits

    if total_gpa_credits <= 0:
        return 0.00
    return round(total_grade_points / total_gpa_credits, 2)


def compute_completed_credits(
    records: List[Any],
    scale: GradingScale,
    block_exempted_credits: int = 0
) -> int:
    """
    Computes total completed credits:
    - Sum of unique course credits where is_pass=True and counts_as_completed=True
      (e.g., standard passes plus EX/CT/HL/PC credit exemptions)
    - Adds block_exempted_credits to the total (block credits apply to total, not specific courses)
    - Repeats of the same course are counted only once
    - Raises ValueError immediately if any course has an unknown grade
    """
    completed_courses: Dict[str, int] = {}

    for rec in records:
        code = getattr(rec, "course_code", None) if not isinstance(rec, dict) else rec.get("course_code")
        grade = getattr(rec, "grade", None) if not isinstance(rec, dict) else rec.get("grade")
        creds = getattr(rec, "credits", None) if not isinstance(rec, dict) else rec.get("credits")

        clean_code = str(code or "").replace(" ", "").upper()
        if not clean_code or not grade:
            continue

        if creds is None:
            raise ValueError(f"Missing credits for {code}")
        credits_val = int(creds)
        defn = scale.get_definition(grade, clean_code)

        if defn.is_pass and defn.counts_as_completed:
            # Completed unique course credits
            completed_courses[clean_code] = credits_val

    course_credits = sum(completed_courses.values())
    return course_credits + max(0, block_exempted_credits)


# ---------------------------------------------------------------------------
# Semester Normalisation & Attempt Selection
# ---------------------------------------------------------------------------
def normalize_semester(label: Union[str, Any]) -> str:
    """
    Normalizes explicit semester and session string representations into the canonical format:
    'SEM <number> <YYYY>/<YYYY>' (e.g. 'SEM 1 2024/2025').

    Accepts ONLY explicit formats:
      1. '(SEM|SEMESTER) <1-4> <YYYY>/<YY or YYYY>' (any case, optional punctuation)
      2. '<YYYY>/<YY or YYYY>-<1-4>' or '<YYYY>/<YY or YYYY> <1-4>'

    All guess fallbacks (single-year -> +1, fall/spring/summer mapping, and bare-digit matching)
    have been removed. Anything else raises ValueError with the raw label (fail loud).
    """
    if not label or not isinstance(label, str) or not label.strip():
        raise ValueError(f"Cannot normalise empty or missing semester label: '{label}'")

    raw = label.strip()

    # Pattern 1: (SEM|SEMESTER) <1-4> <YYYY>/<YY or YYYY>
    # e.g.: "SEM 1 2024/2025", "Sem 1 2024/25", "Semester 1 2024/2025", "SEMESTER 1 SESSION 2024/2025", "SEM: 2, 2023/2024"
    m1 = re.match(
        r'^(?:SEM(?:ESTER)?)\s*[:.]?\s*([1-4])\s*[:.,]?(?:\s*(?:SESSION|SESI))?\s*(\d{4})\s*[\/\-]\s*(\d{4}|\d{2})$',
        raw,
        re.IGNORECASE
    )
    if m1:
        sem_num = int(m1.group(1))
        y1 = int(m1.group(2))
        y2_str = m1.group(3)
        y2 = (y1 // 100) * 100 + int(y2_str) if len(y2_str) == 2 else int(y2_str)
        return f"SEM {sem_num} {y1}/{y2}"

    # Pattern 2: <YYYY>/<YY or YYYY>-<1-4> or <YYYY>/<YY or YYYY> <1-4>
    # e.g.: "2024/2025-1", "2024/2025 1", "2024/2025/1", "2024/25-2", "2024/2025 Sem 1"
    m2 = re.match(
        r'^(\d{4})\s*[\/\-]\s*(\d{4}|\d{2})\s*[-\/\s]\s*(?:SEM(?:ESTER)?\s*[:.]?\s*)?([1-4])$',
        raw,
        re.IGNORECASE
    )
    if m2:
        y1 = int(m2.group(1))
        y2_str = m2.group(2)
        sem_num = int(m2.group(3))
        y2 = (y1 // 100) * 100 + int(y2_str) if len(y2_str) == 2 else int(y2_str)
        return f"SEM {sem_num} {y1}/{y2}"

    raise ValueError(f"Cannot normalise semester label: '{label}'")


def select_attempts_by_repeat_policy(
    records: List[Any],
    scale: GradingScale,
    repeat_policy: str = "latest"
) -> List[Any]:
    """
    Filters a list of course records (ParsedLineItem or CourseAuditResult or dicts),
    returning only the attempt chosen by repeat_policy ('latest' vs 'best') per unique course.
    Preserves input order of the selected attempts.
    """
    if not records:
        return []

    attempts_by_course: Dict[str, List[tuple]] = {}
    for idx, rec in enumerate(records):
        code = getattr(rec, "course_code", None) if not isinstance(rec, dict) else rec.get("course_code")
        grade = getattr(rec, "grade", None) if not isinstance(rec, dict) else rec.get("grade")
        sem = getattr(rec, "semester", None) if not isinstance(rec, dict) else rec.get("semester")

        clean_code = str(code or "").replace(" ", "").upper()
        if not clean_code or not grade:
            continue

        defn = scale.get_definition(grade, clean_code)
        sort_key = _parse_semester_sort_key(str(sem or ""), idx)

        if clean_code not in attempts_by_course:
            attempts_by_course[clean_code] = []
        attempts_by_course[clean_code].append((sort_key, rec, defn, idx))

    chosen_list: List[tuple] = []
    for clean_code, attempts in attempts_by_course.items():
        if len(attempts) == 1:
            chosen_list.append((attempts[0][3], attempts[0][1]))
        else:
            if repeat_policy == "best":
                # Maximize points; if points equal, prefer lower rank; then latest semester
                best_attempt = max(
                    attempts,
                    key=lambda a: (
                        a[2].points if a[2].points is not None else 0.0,
                        -(a[2].rank if a[2].rank is not None else 999),
                        a[0]
                    )
                )
                chosen_list.append((best_attempt[3], best_attempt[1]))
            else:  # 'latest'
                latest_attempt = max(attempts, key=lambda a: a[0])
                chosen_list.append((latest_attempt[3], latest_attempt[1]))

    # Sort back by original index order
    chosen_list.sort(key=lambda x: x[0])
    return [x[1] for x in chosen_list]
