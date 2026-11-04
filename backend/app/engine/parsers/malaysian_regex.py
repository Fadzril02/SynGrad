"""
Smart Academic Assessment System - Malaysian University Regex Parser
"""

import re
from typing import List, Dict, Any, Tuple, Optional

try:
    from app.schemas.audit import ParsedLineItem
    from app.engine.grading import GradingScale, normalize_semester
except ImportError:
    from backend.app.schemas.audit import ParsedLineItem
    from backend.app.engine.grading import GradingScale, normalize_semester


# UTM Course Table Pattern: CODE | COURSE | GR | MN | KR | JMN | ST
# e.g. "SCSE1203 SOFTWARE ENGINEERING PRINCIPLES A 4.00 3 12.00 L" or without ST: "SCSE1203 SOFTWARE ENGINEERING PRINCIPLES A 4.00 3 12.00"
UTM_COURSE_PATTERN = re.compile(
    r'^(?P<code>[A-Z]{2,6}\s*[-]?\s*[0-9]{3,5}[A-Z]?)\s+'
    r'(?P<name>.+?)\s+'
    r'(?P<grade>[A-D][\+\-]?|[EF]|HL|PC|EX|CT|P|LUS|TD|TS|TL)\s+'
    r'(?P<gp>[0-4]\.[0-9]{2})\s+'
    r'(?P<credit>[1-9])\s+'
    r'(?P<jmn>[0-9]+\.[0-9]{2})'
    r'(?:\s+(?P<st>L|G|TD|UM|PK))?'
    r'\s*$',
    re.IGNORECASE
)

# Course-name characters: letters/digits/spaces plus - & / ( ) , . '
COURSE_NAME_CHARS = r"[\w\s\(\)\/\-\,\&\.']"

# Course Regex Pattern (single-line: allows 2 to 6 letters, optional spaces/hyphens, 3 to 5 digits, optional trailing letter)
# Supports optional grade point and optional printed status column (e.g. LULUS, GAGAL, PASS, FAIL, EXEMPT)
COURSE_PATTERN = re.compile(
    r'(?P<code>[A-Z]{2,6}\s*[-]?\s*[0-9]{3,5}[A-Z]?)\s+'
    r'(?P<name>' + COURSE_NAME_CHARS + r'+?)\s+'
    r'(?P<credit>[1-9])\s+'
    r'(?P<grade>[A-D][\+\-]?|[EF]|HL|PC|EX|CT|P|LUS|TD|TS|TL)'
    r'(?:\s+(?P<gp>[0-4]\.[0-9]{2}))?'
    r'(?:\s+(?P<printed_status>PASS(?:ED)?|FAIL(?:ED)?|LULUS|GAGAL|EXEMPT(?:ED)?|PENGECUALIAN))?'
    r'(?:\s+|$)',
    re.IGNORECASE
)

# Alternative Pattern for tabular single-line transcripts
COURSE_PATTERN_ALT = re.compile(
    r'(?P<code>[A-Z]{2,6}\s*[-]?\s*[0-9]{3,5}[A-Z]?)\s+'
    r'(?P<name>.+?)\s+'
    r'(?P<credit>[1-9])\s+'
    r'(?P<grade>[A-D][\+\-]?|[EF]|HL|PC|EX|CT|P|LUS|TD|TS|TL)'
    r'(?:\s+(?P<gp>[0-4]\.[0-9]{2}))?'
    r'(?:\s+(?P<printed_status>PASS(?:ED)?|FAIL(?:ED)?|LULUS|GAGAL|EXEMPT(?:ED)?|PENGECUALIAN))?'
    r'(?:\s+|$)',
    re.IGNORECASE
)

# Individual Token Patterns for Multi-Line / Tabular Block Parsing
CODE_TOKEN_PATTERN = re.compile(r'^[A-Z]{2,6}\s*[-]?\s*[0-9]{3,5}[A-Z]?$', re.IGNORECASE)
# Block start with the title on the same line, e.g. "SCSM2223   CROSS-PLATFORM APPLICATION DEVELOPMENT"
CODE_NAME_LINE_PATTERN = re.compile(
    r'^(?P<code>[A-Z]{2,6}\s*[-]?\s*[0-9]{3,5}[A-Z]?)\s+(?P<name>[A-Z]' + COURSE_NAME_CHARS + r'*)$', re.IGNORECASE
)
GRADE_TOKEN_PATTERN = re.compile(r'^(?:A\+|A|A\-|B\+|B|B\-|C\+|C|C\-|D\+|D|D\-|E|F|HL|PC|EX|CT|P|LUS|TD|TS|TL)$', re.IGNORECASE)
CREDIT_TOKEN_PATTERN = re.compile(r'^[1-9]$')
GP_TOKEN_PATTERN = re.compile(r'^[0-4]\.[0-9]{2}$')
STATUS_TOKEN_PATTERN = re.compile(r'^(?:PASS|PASSED|FAIL|FAILED|LULUS|GAGAL|EXEMPT|EXEMPTED|PENGECUALIAN)$', re.IGNORECASE)
ST_TOKEN_PATTERN = re.compile(r'^(?:L|G|TD|UM|PK)$', re.IGNORECASE)

# Matric Number Pattern (e.g., A20EC0123, A24MJ5050, B21CS0012, SX190204)
MATRIC_PATTERN = re.compile(
    r'(?:MATRIC\s*(?:NO|NUMBER)?|NO\.\s*MATRIK)\s*[:.]?\s*\n?\s*(?::\s*\n?\s*)?([A-Z0-9]{7,12})',
    re.IGNORECASE
)
MATRIC_DIRECT_PATTERN = re.compile(r'\b([A-Z][0-9]{2}[A-Z]{2}[0-9]{4})\b')

# Student Name Pattern - strictly terminates on newline or label keywords
NAME_PATTERN = re.compile(
    r'(?:NAME|NAMA)\s*[:.]?\s*\n?\s*(?::\s*\n?\s*)?([A-Z\s@\/\.\'\-]+?)(?:\r?\n|EXAMINATION|MATRIC|NO\.|FAKULTI|FACULTY|IC\/ISID|$)',
    re.IGNORECASE
)

# Semester / Session Pattern (supports single-line and multi-line formats)
SEMESTER_HEADER_PATTERN = re.compile(r'\b(?:SEMESTER|SEM)\s*[:.]?\s*([1-4])\b', re.IGNORECASE)
SESSION_HEADER_PATTERN = re.compile(r'\b(?:SESSION|SESI)\s*[:.]?\s*(\d{4}\s*[\/\-]\s*(?:\d{4}|\d{2}))\b', re.IGNORECASE)
COMBINED_SEM_SES_PATTERN = re.compile(
    r'\b(?:SEMESTER|SEM)\s*[:.]?\s*([1-4])\s*[:.,]?(?:\s*(?:SESSION|SESI))?\s*(\d{4}\s*[\/\-]\s*(?:\d{4}|\d{2}))\b',
    re.IGNORECASE
)
SEMESTER_PATTERN = re.compile(
    r'(?:SEMESTER|SEM|TERM|TRIMESTER|QUARTER|FALL|SPRING|SUMMER)\s*[:.]?\s*([A-Za-z0-9]+)\s*(?:SESSION|SESI|YEAR)?\s*([0-9]{4}(?:\s*[\/\-]\s*[0-9]{4})?)',
    re.IGNORECASE
)
SEMESTER_SPLIT_SEM = re.compile(r'(?:SEMESTER|SEM)\s*[:.]?\s*([0-9]+)', re.IGNORECASE)
SEMESTER_SPLIT_SES = re.compile(r'(?:SESSION|SESI)\s*[:.]?\s*([0-9]{4}\s*[\/\-]\s*[0-9]{4})', re.IGNORECASE)

# Summary Box Patterns (PNG, PNGK, KK, KD)
PNGK_PATTERN = re.compile(r'\b(?:PNGK|CGPA)\s*[:.]?\s*([0-4]\.[0-9]{2})\b', re.IGNORECASE)
PNG_PATTERN = re.compile(r'\b(?:PNG\b(?!\s*K)|GPA)\s*[:.]?\s*([0-4]\.[0-9]{2})\b', re.IGNORECASE)
KK_PATTERN = re.compile(r'\bKK\b[^\d\n\r]*\b(\d+)\b(?:[^\d\n\r]+\b(\d+)\b)?', re.IGNORECASE)
KD_PATTERN = re.compile(r'\bKD\b[^\d\n\r]*\b(\d+)\b(?:[^\d\n\r]+\b(\d+)\b)?', re.IGNORECASE)


class MalaysianTranscriptParser:
    @staticmethod
    def parse_transcript_lines(
        lines: List[str],
        scale: GradingScale
    ) -> Tuple[Dict[str, Any], List[ParsedLineItem], List[str]]:
        """
        Parses list of text lines extracted from a transcript.
        Normalizes non-breaking spaces and supports both single-line and tabular/multi-line block layouts.
        Performs status cross-check if printed status is present, attaching a warning on disagreement.
        Requires an explicit GradingScale instance.
        """
        if scale is None:
            raise ValueError("scale (GradingScale) is a required parameter for parse_transcript_lines.")

        # 1. Normalize non-breaking spaces (\xa0 -> ' ') and clean whitespace
        cleaned_lines: List[str] = []
        for line in lines:
            c = line.replace('\xa0', ' ').strip()
            if c:
                cleaned_lines.append(c)

        metadata: Dict[str, Any] = {
            "matric_number": None,
            "student_name": None,
            "semesters_found": [],
            "warnings": [],
            "semester": None,
            "academic_session": None,
            "png": None,
            "pngk": None,
            "gpa": None,
            "cgpa": None,
            "kk_this_sem": None,
            "kk_all_sem": None,
            "kd_this_sem": None,
            "kd_all_sem": None,
            "gpa_warning": None
        }
        
        parsed_courses: List[ParsedLineItem] = []
        unparsed_lines: List[str] = []
        
        full_text = "\n".join(cleaned_lines)

        # 2. Extract Matric Number
        matric_match = MATRIC_PATTERN.search(full_text)
        if matric_match:
            metadata["matric_number"] = matric_match.group(1).upper()
        else:
            direct_matric = MATRIC_DIRECT_PATTERN.search(full_text)
            if direct_matric:
                metadata["matric_number"] = direct_matric.group(1).upper()

        # 3. Extract Student Name
        name_match = NAME_PATTERN.search(full_text)
        if name_match:
            raw_name = name_match.group(1).strip()
            # Clean common trailing artifacts
            clean_name = re.sub(r'\s+', ' ', raw_name)
            metadata["student_name"] = clean_name.strip()

        # 4. Extract Global/Header Semesters & Session
        # No default semester: detect "SEMESTER <n>" and "SESSION <yyyy/yyyy>" (or "SESI") on separate lines
        current_semester: Optional[str] = None
        detected_sem_num: Optional[int] = None
        detected_session: Optional[str] = None

        for line in cleaned_lines:
            # Check combined format in a single line (e.g. "SEMESTER 1 SESSION 2024/2025")
            comb_m = COMBINED_SEM_SES_PATTERN.search(line)
            if comb_m:
                detected_sem_num = int(comb_m.group(1))
                detected_session = comb_m.group(2).replace(' ', '')
                break

            if detected_sem_num is None:
                sem_m = SEMESTER_HEADER_PATTERN.search(line)
                if sem_m:
                    detected_sem_num = int(sem_m.group(1))

            if detected_session is None:
                ses_m = SESSION_HEADER_PATTERN.search(line)
                if ses_m:
                    detected_session = ses_m.group(1).replace(' ', '')

        if detected_sem_num is not None and detected_session is not None:
            try:
                norm = normalize_semester(f"SEM {detected_sem_num} {detected_session}")
                current_semester = norm
                if current_semester not in metadata["semesters_found"]:
                    metadata["semesters_found"].append(current_semester)
                metadata["semester"] = detected_sem_num
                parts = current_semester.split()
                if len(parts) >= 3:
                    metadata["academic_session"] = parts[2]
                else:
                    metadata["academic_session"] = detected_session
            except ValueError:
                current_semester = None

        if current_semester is None:
            metadata["warnings"].append("Semester/session not detected")

        # 4b. Extract Summary Box metrics (PNG, PNGK, KK, KD)
        pngk_m = PNGK_PATTERN.search(full_text)
        if pngk_m:
            try:
                val = float(pngk_m.group(1))
                metadata["pngk"] = val
                metadata["cgpa"] = val
            except ValueError:
                pass

        png_m = PNG_PATTERN.search(full_text)
        if png_m:
            try:
                val = float(png_m.group(1))
                metadata["png"] = val
                metadata["gpa"] = val
            except ValueError:
                pass

        kk_m = KK_PATTERN.search(full_text)
        if kk_m:
            try:
                if kk_m.group(2):
                    metadata["kk_this_sem"] = int(kk_m.group(1))
                    metadata["kk_all_sem"] = int(kk_m.group(2))
                else:
                    metadata["kk_all_sem"] = int(kk_m.group(1))
            except (ValueError, TypeError):
                pass

        kd_m = KD_PATTERN.search(full_text)
        if kd_m:
            try:
                if kd_m.group(2):
                    metadata["kd_this_sem"] = int(kd_m.group(1))
                    metadata["kd_all_sem"] = int(kd_m.group(2))
                else:
                    metadata["kd_all_sem"] = int(kd_m.group(1))
            except (ValueError, TypeError):
                pass

        # 5. Course Extraction Loop (Single-Line + Tabular Multi-Line Block Parsing)
        i = 0
        n = len(cleaned_lines)
        stop_keywords = {
            "CODE", "COURSE", "TOTAL", "TOTAL CREDITS", "GPA", "CGPA",
            "This Sem", "All Sem", "GRADING SYSTEM", "PNG", "PNGK",
            "EXAMINATION", "RESULT", "EXAMINATION RESULT", "SEMESTER", "SESSION", "SESI", "KD", "KK", "CE", "JMN"
        }

        while i < n:
            line_str = cleaned_lines[i]
            
            # Check for inline semester header updates (for multi-semester documents)
            sem_inline = COMBINED_SEM_SES_PATTERN.search(line_str) or SEMESTER_PATTERN.search(line_str)
            if sem_inline and not UTM_COURSE_PATTERN.match(line_str):
                try:
                    norm = normalize_semester(sem_inline.group(0))
                    current_semester = norm
                    if current_semester not in metadata["semesters_found"]:
                        metadata["semesters_found"].append(current_semester)
                except ValueError:
                    pass
                i += 1
                continue

            # Path A1: UTM Course Table Pattern: CODE | COURSE | GR | MN | KR | JMN | ST
            utm_m = UTM_COURSE_PATTERN.match(line_str)
            if utm_m:
                raw_code = utm_m.group("code").replace(" ", "").upper()
                name = utm_m.group("name").strip().title()
                credits = int(utm_m.group("credit"))
                grade = utm_m.group("grade").upper()
                st_code = utm_m.group("st")
                gp = float(utm_m.group("gp"))

                is_p = scale.is_pass(grade, raw_code)
                in_cgpa = scale.counts_in_cgpa(grade, raw_code)
                as_comp = scale.counts_as_completed(grade, raw_code)

                if is_p and not in_cgpa and as_comp:
                    status = "Exempted"
                elif is_p:
                    status = "Passed"
                elif grade in {"TD", "TS"}:
                    status = "In-Progress"
                else:
                    status = "Failed"

                item_warnings: List[str] = []
                if current_semester is None:
                    item_warnings.append("Semester/session not detected")

                # ST status column rules
                if st_code:
                    st_clean = st_code.upper()
                    if st_clean == "TD":
                        status = "Withdrawn"
                    elif st_clean == "L" and not is_p:
                        item_warnings.append(
                            f"Discrepancy: Printed transcript status 'L' indicates PASS, but tenant grading scale defines grade '{grade}' as FAIL. Requires advisor verification."
                        )
                    elif st_clean == "G" and is_p:
                        item_warnings.append(
                            f"Discrepancy: Printed transcript status 'G' indicates FAIL, but tenant grading scale defines grade '{grade}' as PASS. Requires advisor verification."
                        )
                    elif st_clean == "UM":
                        item_warnings.append("Repeat course (UM)")
                    elif st_clean == "PK":
                        item_warnings.append("Special exam")

                parsed_courses.append(ParsedLineItem(
                    course_code=raw_code,
                    course_name=name,
                    credits=credits,
                    grade=grade,
                    grade_point=gp,
                    semester=current_semester,
                    status=status,
                    warning="; ".join(item_warnings) if item_warnings else None,
                    is_ai_parsed=False,
                    raw_extracted_text=line_str
                ))
                i += 1
                continue

            # Path A2: Standard Single-Line Regex Match
            single_match = COURSE_PATTERN.search(line_str) or COURSE_PATTERN_ALT.search(line_str)
            if single_match:
                raw_code = single_match.group("code").replace(" ", "").upper()
                name = single_match.group("name").strip().title()
                credits = int(single_match.group("credit"))
                grade = single_match.group("grade").upper()
                printed_status = single_match.groupdict().get("printed_status")

                gp = scale.grade_points(grade, raw_code)
                is_p = scale.is_pass(grade, raw_code)
                in_cgpa = scale.counts_in_cgpa(grade, raw_code)
                as_comp = scale.counts_as_completed(grade, raw_code)

                if is_p and not in_cgpa and as_comp:
                    status = "Exempted"
                elif is_p:
                    status = "Passed"
                elif grade in {"TD", "TS"}:
                    status = "In-Progress"
                else:
                    status = "Failed"

                item_warnings: List[str] = []
                if current_semester is None:
                    item_warnings.append("Semester/session not detected")

                # Status cross-check: Never auto-correct, attach warning on disagreement
                if printed_status:
                    p_clean = printed_status.upper()
                    printed_is_pass = p_clean in {"PASS", "PASSED", "LULUS", "EXEMPT", "EXEMPTED", "PENGECUALIAN"}
                    printed_is_fail = p_clean in {"FAIL", "FAILED", "GAGAL"}

                    if printed_is_pass and not is_p:
                        item_warnings.append(
                            f"Discrepancy: Printed transcript status '{printed_status}' indicates PASS, but tenant grading scale defines grade '{grade}' as FAIL. Requires advisor verification."
                        )
                    elif printed_is_fail and is_p:
                        item_warnings.append(
                            f"Discrepancy: Printed transcript status '{printed_status}' indicates FAIL, but tenant grading scale defines grade '{grade}' as PASS. Requires advisor verification."
                        )

                parsed_courses.append(ParsedLineItem(
                    course_code=raw_code,
                    course_name=name,
                    credits=credits,
                    grade=grade,
                    grade_point=gp,
                    semester=current_semester,
                    status=status,
                    warning="; ".join(item_warnings) if item_warnings else None,
                    is_ai_parsed=False,
                    raw_extracted_text=line_str
                ))
                i += 1
                continue

            # Path B: Multi-Line / Tabular Block Parsing
            code_name_m = CODE_NAME_LINE_PATTERN.match(line_str)
            is_code_candidate = (CODE_TOKEN_PATTERN.match(line_str) or code_name_m) and line_str.upper() not in stop_keywords
            if is_code_candidate:
                code_val = (code_name_m.group("code") if code_name_m else line_str).replace(" ", "").upper()
                block_title: Optional[str] = code_name_m.group("name").strip().title() if code_name_m else None
                block_grade: Optional[str] = None
                block_credits: Optional[int] = None
                block_gp: Optional[float] = None
                block_printed_status: Optional[str] = None
                block_st: Optional[str] = None
                consumed_lines: List[str] = [line_str]

                j = i + 1
                # Scan ahead up to 7 lines for title, grade, credits, grade points, printed status, ST
                while j < min(i + 8, n):
                    candidate_line = cleaned_lines[j]
                    if CODE_TOKEN_PATTERN.match(candidate_line) or CODE_NAME_LINE_PATTERN.match(candidate_line) or any(candidate_line.startswith(kw) for kw in stop_keywords):
                        break

                    consumed_lines.append(candidate_line)

                    # Check for Grade token (e.g. 'A', 'B+', 'HL')
                    if not block_grade and GRADE_TOKEN_PATTERN.match(candidate_line):
                        block_grade = candidate_line.upper()
                    # Check for Grade Point token (e.g. '4.00', '3.33')
                    elif block_gp is None and GP_TOKEN_PATTERN.match(candidate_line):
                        try:
                            block_gp = float(candidate_line)
                        except ValueError:
                            pass
                    # Check for Single-digit Credit Hour token (e.g. '3', '2')
                    elif block_credits is None and CREDIT_TOKEN_PATTERN.match(candidate_line):
                        block_credits = int(candidate_line)
                    # Check for ST status code token (e.g. 'L', 'G', 'TD', 'UM', 'PK')
                    elif not block_st and ST_TOKEN_PATTERN.match(candidate_line):
                        block_st = candidate_line.upper()
                    # Check for Printed Status token (e.g. 'LULUS', 'GAGAL', 'PASS', 'FAIL')
                    elif not block_printed_status and STATUS_TOKEN_PATTERN.match(candidate_line):
                        block_printed_status = candidate_line.strip()
                    # Check for Course Title line (text longer than 2 characters, not purely numbers)
                    elif not block_title and len(candidate_line) > 2 and not re.match(r'^[0-9\.]+$', candidate_line):
                        block_title = candidate_line.strip().title()

                    j += 1

                # If we successfully captured at least code and grade, record the parsed course
                if block_grade:
                    final_credits = block_credits or 3
                    final_gp = block_gp if block_gp is not None else scale.grade_points(block_grade, code_val)
                    is_p = scale.is_pass(block_grade, code_val)
                    in_cgpa = scale.counts_in_cgpa(block_grade, code_val)
                    as_comp = scale.counts_as_completed(block_grade, code_val)

                    if is_p and not in_cgpa and as_comp:
                        status = "Exempted"
                    elif is_p:
                        status = "Passed"
                    elif block_grade in {"TD", "TS"}:
                        status = "In-Progress"
                    else:
                        status = "Failed"

                    item_warnings: List[str] = []
                    if current_semester is None:
                        item_warnings.append("Semester/session not detected")

                    # ST status column rules
                    if block_st:
                        st_clean = block_st.upper()
                        if st_clean == "TD":
                            status = "Withdrawn"
                        elif st_clean == "L" and not is_p:
                            item_warnings.append(
                                f"Discrepancy: Printed transcript status 'L' indicates PASS, but tenant grading scale defines grade '{block_grade}' as FAIL. Requires advisor verification."
                            )
                        elif st_clean == "G" and is_p:
                            item_warnings.append(
                                f"Discrepancy: Printed transcript status 'G' indicates FAIL, but tenant grading scale defines grade '{block_grade}' as PASS. Requires advisor verification."
                            )
                        elif st_clean == "UM":
                            item_warnings.append("Repeat course (UM)")
                        elif st_clean == "PK":
                            item_warnings.append("Special exam")

                    # Status cross-check
                    if block_printed_status:
                        p_clean = block_printed_status.upper()
                        printed_is_pass = p_clean in {"PASS", "PASSED", "LULUS", "EXEMPT", "EXEMPTED", "PENGECUALIAN"}
                        printed_is_fail = p_clean in {"FAIL", "FAILED", "GAGAL"}

                        if printed_is_pass and not is_p:
                            item_warnings.append(
                                f"Discrepancy: Printed transcript status '{block_printed_status}' indicates PASS, but tenant grading scale defines grade '{block_grade}' as FAIL. Requires advisor verification."
                            )
                        elif printed_is_fail and is_p:
                            item_warnings.append(
                                f"Discrepancy: Printed transcript status '{block_printed_status}' indicates FAIL, but tenant grading scale defines grade '{block_grade}' as PASS. Requires advisor verification."
                            )

                    parsed_courses.append(ParsedLineItem(
                        course_code=code_val,
                        course_name=block_title or code_val,
                        credits=final_credits,
                        grade=block_grade,
                        grade_point=final_gp,
                        semester=current_semester,
                        status=status,
                        warning="; ".join(item_warnings) if item_warnings else None,
                        is_ai_parsed=False,
                        raw_extracted_text=" | ".join(consumed_lines)
                    ))
                    i = j
                    continue

            # Path C: Unparsed candidate flagging
            if re.search(r'\b[A-Z]{2,6}\s*[-]?\s*[0-9]{3,5}[A-Z]?\b', line_str) and line_str.upper() not in stop_keywords:
                unparsed_lines.append(line_str)

            i += 1

        # 6. Compute Semester GPA from parsed courses with tenant scale & verify vs printed PNG
        tot_gp = 0.0
        tot_cr = 0
        for c in parsed_courses:
            if scale.counts_in_cgpa(c.grade, c.course_code):
                pts = scale.grade_points(c.grade, c.course_code)
                tot_gp += (pts * c.credits)
                tot_cr += c.credits

        computed_gpa = round(tot_gp / tot_cr, 2) if tot_cr > 0 else 0.00
        metadata["computed_semester_gpa"] = computed_gpa

        if metadata.get("png") is not None:
            printed_png = metadata["png"]
            if abs(computed_gpa - printed_png) > 0.01:
                gpa_warn = f"GPA mismatch with transcript (computed {computed_gpa:.2f} vs printed {printed_png:.2f})"
                metadata["gpa_warning"] = gpa_warn
                if gpa_warn not in metadata["warnings"]:
                    metadata["warnings"].append(gpa_warn)

        return metadata, parsed_courses, unparsed_lines
