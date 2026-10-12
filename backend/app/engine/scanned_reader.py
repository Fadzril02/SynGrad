"""
SynGrad - Scanned Transcript Slip Reader (Vision Model Integration)
Extracts transcript data from scanned/image-only PDFs via multimodal vision model.
Renders pages with PyMuPDF (~200 dpi, max 2000px long side, max 6 pages).
In-memory processing only: images are never stored or persisted.
Strict PDPA privacy: never output or retain national IDs (IC/NRIC/MyKad) or passport numbers.
"""

import base64
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import fitz  # PyMuPDF
from fastapi import HTTPException, status
from openai import OpenAI

try:
    from app.core.config import settings
    from app.engine.universal_reader import (
        looks_like_national_id,
        redact_personal_ids,
        _clean_json_content,
        _NRIC_RE,
    )
except ImportError:
    from backend.app.core.config import settings
    from backend.app.engine.universal_reader import (
        looks_like_national_id,
        redact_personal_ids,
        _clean_json_content,
        _NRIC_RE,
    )

logger = logging.getLogger("syngrad.scanned_reader")

MAX_SCANNED_PAGES = 6

VISION_SYSTEM_PROMPT = """You are an academic transcript data extractor analyzing an image of an academic transcript slip.
Your task is to accurately extract course records, semester details, printed GPA/CGPA, and student registration/matriculation number from the provided page image.

Institution context:
- Recognized grade symbols: {valid_grades_context}

Return a single JSON object strictly matching this schema:
{{
  "semesters": [
    {{
      "semester_no": 1,
      "session": "YYYY/YYYY",
      "courses": [
        {{
          "code": "COURSE_CODE",
          "name": "COURSE_NAME",
          "credits": 3,
          "grade": "GRADE"
        }}
      ],
      "printed_gpa": null,
      "printed_cgpa": null
    }}
  ],
  "matric_no": null
}}

Extraction Rules:
1. Do not invent or hallucinate courses. Extract only records present on this page image. If no courses are found on this page, return an empty "semesters" list [].
2. "semester_no" must be an integer (1 to 4).
3. "session" must be the academic year format "YYYY/YYYY" (e.g. "2024/2025" or "2023/2024").
4. "credits" must be a positive number.
5. "printed_gpa" and "printed_cgpa" are the GPA and CGPA values explicitly printed on the slip for that semester (decimal number), or null if not printed.
6. "matric_no" is the student matric/registration number if found, or null. NEVER output national ID (IC/NRIC/MyKad) or passport numbers anywhere; ignore them completely.
7. Return raw JSON only with NO markdown fences, NO preamble, and NO extra keys.
"""


def render_pdf_to_images(pdf_bytes: bytes) -> List[bytes]:
    """
    Renders PDF pages to PNG bytes in memory using PyMuPDF.
    Enforces ~200 dpi, long side <= 2000px, max 6 pages.
    Never writes images to disk or external storage.
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to read PDF structure: {e}",
        )

    page_count = len(doc)
    if page_count > MAX_SCANNED_PAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please upload at most 6 pages",
        )
    if page_count == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF contains no readable pages.",
        )

    images: List[bytes] = []
    for page in doc:
        max_pt = max(page.rect.width, page.rect.height)
        if max_pt <= 0:
            max_pt = 1.0

        desired_scale = 200.0 / 72.0
        # If ~200 dpi would exceed 2000px on the longest side, cap at 2000px
        if max_pt * desired_scale > 2000.0:
            scale = 2000.0 / max_pt
        else:
            scale = desired_scale

        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix)
        png_bytes = pix.tobytes("png")
        images.append(png_bytes)

    return images


def extract_page_with_vision(
    png_bytes: bytes,
    tenant_ctx: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Calls vision-capable model through OpenAI-compatible client for a single page image.
    Timeout + 1 retry per call.
    """
    if not settings.LLM_VISION_MODEL:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Scanned slips aren't supported yet — please upload the original PDF from your student portal.",
        )
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM API key is not configured for vision transcript extraction.")

    tenant_ctx = tenant_ctx or {}
    valid_grades = tenant_ctx.get("valid_grades", [])
    valid_grades_context = (
        ", ".join(valid_grades)
        if valid_grades
        else "Standard letter grades (A-F, plus/minus, pass/fail codes)"
    )

    system_prompt = VISION_SYSTEM_PROMPT.format(valid_grades_context=valid_grades_context)
    b64_image = base64.b64encode(png_bytes).decode("utf-8")

    client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        timeout=35.0,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Extract transcript data from this transcript page image. Never output national ID (IC/NRIC/MyKad) or passport numbers.",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64_image}"
                    },
                },
            ],
        },
    ]

    last_error: Optional[Exception] = None
    content: Optional[str] = None

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=settings.LLM_VISION_MODEL,
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=2500,
            )
            content = response.choices[0].message.content or ""
            break
        except Exception as e:
            last_error = e
            logger.warning(f"[ScannedReader] Vision extraction attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                continue

    if content is None:
        raise RuntimeError(f"Vision transcript extraction failed after retry: {last_error}")

    cleaned = _clean_json_content(content)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as err:
        raise ValueError(f"Vision model returned invalid JSON: {err}\nContent: {cleaned[:300]}")

    semesters = parsed.get("semesters")
    if not isinstance(semesters, list):
        semesters = []

    conformed_semesters: List[Dict[str, Any]] = []
    for sem in semesters:
        if not isinstance(sem, dict):
            continue

        raw_sem_no = sem.get("semester_no")
        sem_no = 1
        if raw_sem_no is not None:
            try:
                sem_no = int(raw_sem_no)
            except (ValueError, TypeError):
                sem_no = 1

        session = str(sem.get("session") or "").strip()
        session = re.sub(r"(\d{4})[-\s](\d{4})", r"\1/\2", session)

        courses_list = sem.get("courses") or []
        conformed_courses: List[Dict[str, Any]] = []
        for c in courses_list:
            if not isinstance(c, dict):
                continue
            code = str(c.get("code") or c.get("course_code") or "").strip().upper()
            name = str(c.get("name") or c.get("course_name") or code).strip()
            raw_creds = c.get("credits") or c.get("credit_hour") or 3
            try:
                creds = float(raw_creds)
                if creds.is_integer():
                    creds = int(creds)
            except (ValueError, TypeError):
                creds = 3

            grade = str(c.get("grade") or "").strip().upper()

            # PRIVACY POST-FILTER: drop/null values looking like national IDs
            if looks_like_national_id(code) or looks_like_national_id(name) or looks_like_national_id(grade):
                continue
            name = redact_personal_ids(name)

            conformed_courses.append({
                "code": code,
                "name": name,
                "credits": creds,
                "grade": grade,
            })

        printed_gpa = sem.get("printed_gpa")
        if printed_gpa is not None:
            try:
                printed_gpa = float(printed_gpa)
            except (ValueError, TypeError):
                printed_gpa = None

        printed_cgpa = sem.get("printed_cgpa")
        if printed_cgpa is not None:
            try:
                printed_cgpa = float(printed_cgpa)
            except (ValueError, TypeError):
                printed_cgpa = None

        conformed_semesters.append({
            "semester_no": sem_no,
            "session": session,
            "courses": conformed_courses,
            "printed_gpa": printed_gpa,
            "printed_cgpa": printed_cgpa,
        })

    raw_matric = parsed.get("matric_no") or parsed.get("matric_number")
    matric_no = str(raw_matric).strip().upper() if raw_matric else None
    if looks_like_national_id(matric_no):
        matric_no = None

    return {
        "semesters": conformed_semesters,
        "matric_no": matric_no,
    }


def extract_scanned_transcript(
    pdf_bytes: bytes,
    tenant_ctx: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Full pipeline for scanned transcript:
    1. Render pages to PNG (max 6, ~200 dpi, <=2000px).
    2. Extract each page with vision model.
    3. Merge semesters across pages.
    4. Post-filter national IDs.
    5. Add warnings for unreadable pages (0 courses).
    """
    if not settings.LLM_VISION_MODEL:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Scanned slips aren't supported yet — please upload the original PDF from your student portal.",
        )

    pages = render_pdf_to_images(pdf_bytes)

    merged_semesters: List[Dict[str, Any]] = []
    semester_map: Dict[Tuple[int, str], Dict[str, Any]] = {}
    detected_matric_no: Optional[str] = None
    page_warnings: List[str] = []

    for page_idx, png_bytes in enumerate(pages, start=1):
        page_res = extract_page_with_vision(png_bytes, tenant_ctx)
        p_semesters = page_res.get("semesters", [])
        total_page_courses = sum(len(s.get("courses", [])) for s in p_semesters)

        if total_page_courses == 0:
            page_warnings.append(f"Page {page_idx} could not be read")

        if not detected_matric_no and page_res.get("matric_no"):
            candidate_matric = page_res.get("matric_no")
            if not looks_like_national_id(candidate_matric):
                detected_matric_no = candidate_matric

        for s in p_semesters:
            sem_key = (s.get("semester_no", 1), s.get("session", ""))
            if sem_key not in semester_map:
                new_sem = {
                    "semester_no": sem_key[0],
                    "session": sem_key[1],
                    "courses": list(s.get("courses", [])),
                    "printed_gpa": s.get("printed_gpa"),
                    "printed_cgpa": s.get("printed_cgpa"),
                }
                semester_map[sem_key] = new_sem
                merged_semesters.append(new_sem)
            else:
                existing = semester_map[sem_key]
                existing["courses"].extend(s.get("courses", []))
                if existing.get("printed_gpa") is None and s.get("printed_gpa") is not None:
                    existing["printed_gpa"] = s.get("printed_gpa")
                if existing.get("printed_cgpa") is None and s.get("printed_cgpa") is not None:
                    existing["printed_cgpa"] = s.get("printed_cgpa")

    # Post-filter privacy checks across entire merged structure
    if looks_like_national_id(detected_matric_no):
        detected_matric_no = None

    for sem in merged_semesters:
        filtered_courses = []
        for c in sem.get("courses", []):
            code = c.get("code", "")
            name = c.get("name", "")
            grade = c.get("grade", "")
            if looks_like_national_id(code) or looks_like_national_id(name) or looks_like_national_id(grade):
                continue
            c["name"] = redact_personal_ids(name)
            filtered_courses.append(c)
        sem["courses"] = filtered_courses

    return {
        "semesters": merged_semesters,
        "matric_no": detected_matric_no,
        "warnings": page_warnings,
    }
