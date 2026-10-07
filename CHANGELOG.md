# Changelog

Newest first. Tag format `v0.x-name`. Note: git tags for these milestones are not created yet; create them on the matching commits.

## Unreleased
- Universal transcript slip reader (multi-university foundation, Roadmap 5):
  - Migration 36: `tenants.slip_profile` (TEXT NULL) to support university rule parsers ('utm') vs universal AI reader (NULL).
  - Backend universal reader (`backend/app/engine/universal_reader.py`): ONE LLM call to Groq/OpenAI-compatible client with strict academic JSON schema (`semesters`, `courses`, `printed_gpa`, `printed_cgpa`, `matric_no`), input size cap, timeout, 1 retry, temperature 0. Fails loud with clear error if API key is missing.
  - Zero-Waste decision in `POST /audit/extract`: runs rule parser if `slip_profile == 'utm'` and confident; otherwise routes to universal reader (`source='ai'`). Scanned PDFs with no extractable text layer fail with HTTP 422 ("Scanned slips aren't supported yet — please upload the original PDF from your student portal.").
  - Pure guardrails (`backend/app/engine/slip_validation.py`): checks grade scale existence, positive credits (flags decimal credits as unsupported), course code format sanity, semester normalisation, GPA recalculation cross-check (0.01 tolerance), and student matric cross-match ("This slip may belong to someone else" blocking warning). Never alters values.
  - Multi-semester transcripts: courses carry per-course `session_semester` across student verification and advisor approval to persist attempts under their respective academic semesters.
  - Frontend verification (`StudentPortal.tsx`) & corrections (`CorrectionsQueue.tsx`): display "Read by AI" banner when `source='ai'`, warning alerts above tables, matric mismatch blocks submission/approval, and per-row semester column rendered for multi-semester transcripts.

## v0.7-template-editor (2026-10-02)
- Roadmap 4 complete: requirement engine (4A, migs 31–32), manual elective override (4B, mig 33), progress perf (mig 35), template editor (4C, mig 34).
- Fixes: py3.12 `Optional` import crash, missing `useRef`, pinned action columns, curriculum upload credits input.
- Migration 34: `degree_templates.owner_staff_id` (TEXT NULL) tracking uploader advisor; `template_courses.updated_at` (TIMESTAMPTZ).
- Curriculum template editor (SynGrad roadmap 4C):
  - Uploader-only edit governance: only the advisor who uploaded a degree template can edit it; other tenant advisors have read-only access (`can_edit: false`); NULL owner returns 403 ("Template has no owner; contact support").
  - Backend endpoints (`courses.py`): `GET /courses/templates`, `GET /courses/templates/{id}`, `PATCH /courses/templates/{id}`, `POST /courses/templates/{id}/rows`, `PATCH /courses/templates/{id}/rows/{row_id}`, `DELETE /courses/templates/{id}/rows/{row_id}`, `GET /courses/templates/{id}/rows/{row_id}/impact`.
  - Single-row validator refactor (`CSVCourseParser.validate_course_row`) shared identically by CSV upload and row editor endpoints (handles course code format, slot detection with `/` or `XX`, credits > 0, category required, prerequisite string parsing with min_credits and min_grade, and duplicate real course code rejection with 422).
  - Automatic slot renumbering (1..n) after row additions and deletions; slot deletion cascades linked `elective_assignments` and returns count.
  - Advisor frontend "Curriculum" view (`CurriculumTemplatesView.tsx`): template directory, editable course table, live credits tally comparison ("Rows total X / programme Y credits"), inline 422 error display per row, read-only mode banner for non-uploaders, and deletion impact confirmation modal.
- Migration 33: `elective_assignments` table for manual elective overrides (kind='assign' or 'exclude'). Unique `(tenant_id, matric_no, course_code)`, partial unique index on slot for assign. RLS select-only for student own / advisor advisee; writes via backend service role only.
- Manual elective override (SynGrad roadmap 4B): `PUT` and `DELETE` `/audit/progress/{matric_no}/overrides` endpoints (advisor only, advisee check, JWT-derived tenant/advisor ID). Engine slot pinning, course exclusions, stale override fallback with warnings, and bipartite override precedence. Advisor interactive override & exclusion controls in `StudentView.tsx`; read-only badges in student `DegreeAuditView.tsx`.
- Migration 30: `academic-slips` bucket private; uploads only to own `slips/<matric>_...` path; reads only for files listed in `uploaded_documents` the user can see; `degree_audits` read policies.
- Removed `/audit/process-storage` (bypassed student verification) and dead `src/pages/advisor/` + `StudentRadarChart`.
- `/health` stripped to `{status, environment}`.
- Fix: extract crashed saving results (`doc` shadowed by PyMuPDF document).
- CORS: wildcard origins replaced with `BACKEND_CORS_ORIGIN_REGEX`.
- DEPLOYMENT.md (staging/production plan).

## v0.5-upload-security
- Extraction results stored server-side (`original_courses`); student confirms via `/audit/submit-verification`; server computes `is_altered`.
- Ownership checks on extract, finalize, reject. Migration 29 locks `uploaded_documents`.

## v0.4-frontend-grading
- Frontend uses tenant grade scale; advisor exemptions screen; roster view computes CGPA from grade scale (migration 28).

## v0.3-grading-scale
- `grade_scales` per tenant + presets (migration 26). Multi-attempt records with repeat policy (migration 27).

## v0.2-advising-notes
- Advising logs v2, student read view, email notification via Resend, 1/student/hour (migrations 24–25).

## v0.1-uat-working
- Tenants, advisor invites, RLS lockdown, elective slots, cohort lockdown (migrations 17–23). Sign-up → upload → approve flow working.
