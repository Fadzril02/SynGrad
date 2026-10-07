"""
SynGrad - Universal Transcript Slip Reader (Zero-Waste & Multi-University Foundation)
Provides LLM-based universal slip parsing conforming to strict academic schema.
ONE call per slip, temperature 0, JSON output, timeout, 1 retry, input size cap.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from openai import OpenAI

try:
    from app.core.config import settings
except ImportError:
    from backend.app.core.config import settings

logger = logging.getLogger("syngrad.universal_reader")

MAX_INPUT_CHAR_LIMIT = 20000

UNIVERSAL_SYSTEM_PROMPT = """You are an academic transcript data extractor.
Your task is to accurately extract course records, semester details, printed GPA/CGPA, and student registration/matriculation number from the provided academic transcript text.

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
1. Do not invent or hallucinate courses. Extract only records present in the text.
2. "semester_no" must be an integer (1 to 4).
3. "session" must be the academic year format "YYYY/YYYY" (e.g. "2024/2025" or "2023/2024").
4. "credits" must be a positive number.
5. "printed_gpa" and "printed_cgpa" are the GPA and CGPA values explicitly printed on the slip for that semester (decimal number), or null if not printed.
6. "matric_no" is the student ID/matric number if found, or null.
7. Return raw JSON only with NO markdown fences, NO preamble, and NO extra keys.
"""


def _clean_json_content(content: str) -> str:
    """Strip markdown code block fences if returned by the LLM."""
    content = content.strip()
    if content.startswith("```"):
        # Split on triple backticks
        parts = content.split("```")
        if len(parts) >= 2:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[4:]
            content = inner.strip()
    return content


def extract_with_llm(text: str, tenant_ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extracts transcript data using Groq/OpenAI-compatible client.
    ONE call per slip, temperature 0, JSON output, timeout, 1 retry, input size cap.
    Raises RuntimeError/ValueError if LLM API key is missing or parsing fails.
    """
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM API key is not configured for universal transcript extraction.")

    tenant_ctx = tenant_ctx or {}
    valid_grades = tenant_ctx.get("valid_grades", [])
    valid_grades_context = ", ".join(valid_grades) if valid_grades else "Standard letter grades (A-F, plus/minus, pass/fail codes)"

    system_prompt = UNIVERSAL_SYSTEM_PROMPT.format(valid_grades_context=valid_grades_context)
    capped_text = text[:MAX_INPUT_CHAR_LIMIT]

    client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        timeout=35.0,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Extract transcript data from this text:\n\n{capped_text}"},
    ]

    # Attempt call with 1 retry on failure
    last_error: Optional[Exception] = None
    content: Optional[str] = None

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=2500,
            )
            content = response.choices[0].message.content or ""
            break
        except Exception as e:
            last_error = e
            logger.warning(f"[UniversalReader] LLM extraction attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                continue

    if content is None:
        raise RuntimeError(f"Universal transcript extraction failed after retry: {last_error}")

    cleaned = _clean_json_content(content)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as err:
        raise ValueError(f"LLM returned invalid JSON for transcript extraction: {err}\nContent: {cleaned[:300]}")

    # Conform to standard schema
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
        # Clean session format if e.g. "2024-2025" -> "2024/2025"
        session = re.sub(r'(\d{4})[-\s](\d{4})', r'\1/\2', session)

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

    return {
        "semesters": conformed_semesters,
        "matric_no": matric_no,
    }
