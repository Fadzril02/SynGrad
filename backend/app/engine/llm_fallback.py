"""
Smart Academic Assessment System - Micro-LLM Fallback Module (Zero-Waste)
"""

import json
from typing import List, Optional
try:
    from app.core.config import settings
    from app.schemas.audit import ParsedLineItem
except ImportError:
    from backend.app.core.config import settings
    from backend.app.schemas.audit import ParsedLineItem


FALLBACK_SYSTEM_PROMPT = """You are a specialized Malaysian University Transcript line parser.
You extract ONLY course records from ambiguous text lines.
Output valid JSON array of objects with keys:
- course_code (string, e.g. SECJ1013)
- course_name (string)
- credits (integer)
- grade (string, e.g. A, B+, HL)
- grade_point (float, e.g. 4.0, 3.33, 0.0)
- status (string: 'Passed', 'Failed', 'Exempted', or 'In-Progress')
Do NOT invent courses. If line is not a course, return empty array [].
Output raw JSON only without markdown fences."""


class MicroLLMFallback:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        # Built on first use so importing this module doesn't load the openai SDK
        if self._client is None and settings.LLM_API_KEY:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL
            )
        return self._client

    def parse_ambiguous_lines(self, lines: List[str], current_semester: str = "Transferred") -> List[ParsedLineItem]:
        """
        Micro-LLM fallback used strictly when regex parser fails on ambiguous lines.
        """
        if not self.client or not lines:
            return []

        try:
            prompt = f"Parse these ambiguous Malaysian transcript lines:\n" + "\n".join(lines[:10])
            response = self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": FALLBACK_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=500
            )

            content = response.choices[0].message.content.strip()
            # Remove any markdown backticks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            items = json.loads(content.strip())
            results: List[ParsedLineItem] = []
            for item in items:
                results.append(ParsedLineItem(
                    course_code=item.get("course_code", "UNKNOWN").replace(" ", "").upper(),
                    course_name=item.get("course_name", "Unknown Course").title(),
                    credits=int(item.get("credits", 3)),
                    grade=item.get("grade", "HL").upper(),
                    grade_point=float(item.get("grade_point", 0.0)),
                    semester=current_semester,
                    status=item.get("status", "Exempted"),
                    is_ai_parsed=True,
                    raw_extracted_text="[AI FALLBACK] " + prompt
                ))
            return results
        except Exception as e:
            # Fallback gracefully without breaking pipeline
            print(f"[LLM Fallback Warning] Micro-LLM invocation skipped: {str(e)}")
            return []
