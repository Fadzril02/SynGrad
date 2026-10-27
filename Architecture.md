# SynGrad — Architecture

Updated 2026-10-26. Product scope: `PRD.md`. Source of truth for schema: `supabase/migrations/`.

## System flow (current)
1. Advisor signs up via invite link.
2. Advisor uploads course structure CSV.
3. Advisor creates a cohort code.
4. Student signs up: cohort code + email domain + matric format check.
5. Student uploads a result slip.
6. Fraud check.
7. Reader routing: `rules` (text parser) / `ai` (LLM, IC numbers redacted first) / `ai_scan` (vision for scanned slips).
8. Guardrails validate codes, credits, grades: they **flag, never correct**.
9. Student verifies the extracted rows.
10. Advisor approves (422 if any credits missing; slip purged) or rejects (slip purged).
11. Degree audit + cohort roster update.

Cold start: frontend calls `warmUpBackend` and shows a notice while Render wakes. `/lab` (Slip Lab) is staging only.

## Planned (not built)
- **Single-player mode:** any email, no cohort/advisor; pick Institution → Programme → Intake.
- **Curriculum library:** structures per institution + programme + intake, versioned, never overwritten. Student edits = private copy. Trust levels: extracted → student-confirmed → advisor-verified. Promote when 2 identical student versions exist or an advisor approves.
- **Handbook extraction:** file-hash cache → PDF text + regex → LLM strict JSON in the existing CSV format → `CSVCourseParser` → credit-total checks → review only flagged rows. Unparseable = "not checked".
- **Grade scale:** presets (standard 4.00, UM, polytechnic, custom) + pass grade + special codes; auto-pick by matching the printed GPA; add an in-progress flag (removes hardcoded TD/TS).
- **Retired courses:** "retired from intake X"; `course_equivalences` table (old↔new code, institution, from intake); unmapped → "Not counted — needs review".
- **Semester load:** min/max credits per semester (+ override, + CGPA-based max); credit gates via existing `min_credits`.

## 1. Topology

```
Vercel: React 19 + Vite SPA ──(Supabase JS: auth, RLS reads, slip upload)──> Supabase (Auth, Postgres, Storage)
        │                                                                        ▲
        └──(axios, Bearer JWT)──> Render: FastAPI (Python 3.12) ──(service role)─┘
                                       ├─> Groq (OpenAI-compatible): LLM_MODEL, LLM_VISION_MODEL
                                       └─> Resend (advising notification email)
```

| Part | Key files |
|---|---|
| Routes | `src/app/App.tsx` (`/`, `/complete-registration`, `/student/*`, `/advisor/*`, `/lab` staging only) |
| API client | `src/lib/api.ts` (`apiClient`, `warmUpBackend`, slow-request notice, token refresh) |
| Auth (frontend) | `src/context/AuthContext.tsx`, `src/lib/supabase.ts` |
| Backend entry | `backend/app/main.py`, `backend/app/v1/router.py`, `backend/app/core/{config,auth,supabase_client}.py` |
| Slip engine | `backend/app/v1/endpoints/audit.py` (`run_slip_extraction`), `backend/app/engine/{universal_reader,scanned_reader,slip_validation,grading,progress}.py`, `engine/parsers/` |

## 2. Data model
- Multi-university. Every row is scoped by `tenant_id` (TEXT, e.g. `'UTM'`). No faculty layer.
- Nothing university-specific in code or CHECK constraints; it lives in `tenants`, `grade_scales`, templates.

| Table | Notes |
|---|---|
| `tenants` | `student_email_domains TEXT[]` (one or more; non-empty), `staff_email_domains[]`, `matric_regex`, `min_pass_grade`, `default_prereq_min_grade`, `repeat_policy`, `slip_profile` (`'utm'` = rules parser; NULL = AI only). `tenants_public` view exposes id/name. |
| `grade_scales` | per tenant: grade, point, min/max mark, `is_pass`, `achievement_label`; special codes (HL, EX, CT, TD, TS). Presets in `grade_scale_presets`, `clone_preset_to_tenant()` |
| `advisor_invites` | invite codes for advisor registration |
| `advisors`, `students` | identity columns protected by triggers; `students.matric_no` globally unique (blocks same matric at two tenants — fix before 2nd university) |
| `cohorts` | cohort code → template; students join with code; `is_locked` |
| `degree_templates`, `template_courses` | tenant-scoped curriculum; `owner_staff_id` (mig 34) = uploader-only editing; elective slots = code containing `/` or `XX`, auto-numbered, `match_patterns` |
| `academic_records` | one row per attempt, unique `(tenant_id, matric_no, course_code, semester)`; semester normalised `SEM n YYYY/YYYY`; `repeat_policy` picks the counted attempt |
| `uploaded_documents` | slip metadata, `extracted_data` incl. server-side `original_courses`, `processing_status`, `fraud_flag`; browser cannot write status/results (mig 29); `file_path = '[PURGED]'` after deletion |
| `advising_logs` | advisor notes, student reads own; `created_at`/matric/advisor locked on UPDATE; notification sent-at for rate limit |
| `degree_audits` | audit snapshots; read: own student or own advisor (mig 30) |
| `elective_assignments` | manual elective overrides (mig 33): assign/exclude |
| `exemption_audit` | exemption history |
| view `advisee_roster_summary` | `security_invoker = true`; CGPA/credits from tenant grade scale |

## 3. Security
- **RLS**: SECURITY DEFINER helpers `my_staff_ids()`, `my_advisor_staff_ids()`, `my_matric_nos()`, `my_advisee_matric_nos()`, `my_tenant_id()`. Students see own rows, advisors their advisees', anon nothing. Identity-protect triggers bypass only with no JWT claims (SQL editor) or `service_role`.
- **Storage** bucket `academic-slips` (private, mig 30): INSERT only to `slips/<own matric>_<ts>.<ext>`; SELECT only for paths in visible `uploaded_documents` rows. Advisors view via 1 h signed URL.
- **Identity**: backend verifies Supabase ES256 JWT via JWKS (cached 1 h). `advisor_id`, `tenant_id`, `matric_no` come from JWT/app_metadata or DB lookup, never the body. Role + tenant written to `app_metadata` by `/register/*`. Document access goes through `_load_authorized_document()` in `audit.py`.
- Unhandled exceptions return a generic 500 (no stack trace to client). Boot fails if `SUPABASE_SERVICE_ROLE_KEY` is missing.

## 4. API (prefix `/api/v1`)
| Endpoint | Who | Purpose |
|---|---|---|
| `GET /health` | public | `{status, environment}`; also the warm-up ping |
| `POST /register/student` | new user | cohort code + matric + name; email domain ∈ `student_email_domains`; matric vs `matric_regex`; duplicate → 409 |
| `POST /register/advisor` | new user | invite code |
| `GET /register/validate-cohort/{code}` | public | cohort lookup |
| `POST /courses/upload-csv`, `GET /courses/template-csv` | advisor | curriculum upload (sets `owner_staff_id`) / blank template |
| `GET /courses/templates`, `GET /courses/templates/{id}` | advisor | list (with `can_edit`) / detail |
| `PATCH /courses/templates/{id}`, `POST·PATCH·DELETE …/rows[/{row_id}]`, `GET …/rows/{row_id}/impact` | advisor (owner) | template editor; delete cascades overrides and renumbers slots |
| `POST /audit/extract` | student/advisor (owner) | read slip (§5), save results server-side |
| `POST /audit/submit-verification` | student | confirm/edit rows; server computes `is_altered` vs `original_courses` |
| `POST /audit/finalize-approval` | advisor (own advisee) | write `academic_records` (per-course `session_semester`), then purge slip |
| `POST /audit/reject-document` | advisor (own advisee) | mark Rejected, then purge slip |
| `POST /audit/purge-document` | advisor | purge an Approved document's file |
| `GET /audit/progress/{matric_no}` | student (own) / advisor | degree progress |
| `PUT /audit/progress/{matric_no}/overrides`, `DELETE …/overrides/{course_code}` | advisor | elective assign/exclude / remove |
| `PATCH /students/{matric_no}/exemptions` | advisor | exemptions |
| `POST /advising-logs/{log_id}/notify` | advisor | Resend email, no note text, 1/student/hour |
| `POST /lab/extract` | staging staff | Slip Lab (§6). Also mounted without prefix at `/lab/extract` |

## 5. Slip pipeline (`run_slip_extraction`)
1. **Fraud check**: PDF creator/producer from editing tools → `fraud_flag`.
2. **Text layer** via PyMuPDF. No text and no `LLM_VISION_MODEL` → 422 "Scanned slips aren't supported yet — please upload the original PDF from your student portal." (no silent fallback).
3. **Rules** (`slip_profile == 'utm'`): used if confident (semester + session, ≥1 course, 0 unparsed lines) → `source='rules'`.
4. **Universal AI reader** otherwise: text passed through `redact_personal_ids()` (NRIC pattern + values after IC/K/P/passport labels → `[REDACTED-ID]`), capped, ONE call to `LLM_MODEL` (default `llama-3.1-8b-instant`), JSON mode, temperature 0, 1 retry → `source='ai'`.
5. **Scanned** (no text layer): `scanned_reader.py` renders pages to PNG (~200 dpi, long side ≤ 2000 px, max 6 pages; more → 422), one call per page to `LLM_VISION_MODEL` (currently `qwen/qwen3.8-27b`, set by env; unset = disabled), 35 s timeout + 1 retry. Pages merged by `(semester_no, session)`; "Page N could not be read" warning for empty pages. Images in memory only → `source='ai_scan'`.
6. **PDPA post-filter** (all AI paths): prompt forbids IC/passport output; any value matching `looks_like_national_id()` is dropped (never kept as `matric_no`); names/codes redacted.
7. **Guardrails** (`engine/slip_validation.py`, pure): grade in tenant scale, credits > 0 (decimals flagged), course-code sanity, semester normalisation, printed vs recomputed GPA (±0.01), slip matric vs expected (blocking "This slip may belong to someone else"). Warnings + `needs_review` only; values never changed.
8. **Purge**: after approve **and** after reject, the file is deleted from `academic-slips` and `file_path` set to `[PURGED]`. On reject a failed delete is logged and `file_path` kept so it can be removed later; the rejection still stands.

## 6. Slip Lab (staging only)
- `POST /lab/extract` (multipart PDF + `tenant_id`): same pipeline as §5, returns `{source, model, semesters, courses, warnings, needs_review, timing}`. No DB writes, no storage.
- 404 unless `ENVIRONMENT == "staging"`; 403 unless JWT email ∈ `LAB_ALLOWED_EMAILS` (comma-separated).
- Frontend `/lab` route exists only when `VITE_ENVIRONMENT === 'staging'` (or Vite mode `staging`).

## 7. Cold start & startup
- Render free tier sleeps. `warmUpBackend()` fires one unauthenticated `GET /api/v1/health` per page load (landing, complete-registration); no retries, errors ignored.
- `apiClient` shows one shared sonner toast (id `server-waking`) when any request is pending > 5 s; dismissed when the last slow request settles. Axios timeout 75 s.
- Lazy imports: `pymupdf` and the `openai` SDK are imported inside the functions that use them; `MicroLLMFallback.client` is built on first use. `tests/test_lazy_imports.py` asserts `import app.main` loads neither.

## 8. Config (env)
Backend: `ENVIRONMENT`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `LLM_API_KEY` (or `GROQ_API_KEY`), `LLM_BASE_URL` (default Groq), `LLM_MODEL`, `LLM_VISION_MODEL`, `LAB_ALLOWED_EMAILS`, `RESEND_API_KEY`, `RESEND_FROM`, `FRONTEND_URL`, `BACKEND_CORS_ORIGINS` / `BACKEND_CORS_ORIGIN_REGEX`.
Frontend: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`, `VITE_ENVIRONMENT`.

## 9. Migrations (applied in order; never edit after applied)
01–16 legacy (written against a drifted DB; staging is built from a prod schema dump). 17 tenant curriculum · 18 tenants · 19 advisor_invites · 20 RLS lockdown · 21 drop email advisor policies · 22 elective slots · 23 cohorts lockdown · 24 advising_logs v2 · 25 advising notifications · 26 grading scales · 27 record attempts · 28 roster view · 29 uploaded_documents lockdown · 30 storage + degree_audits RLS (**apply after push**) · 31 template_courses category · 32 template_courses course_code text · 33 elective_assignments · 34 template owner · 35 progress indexes · 36 tenant slip_profile. From 30 on: staging first, then prod.

## 10. Known gaps
- `DegreeAuditView.tsx` has a UTM course-prefix regex; `src/lib/tenants.ts` has a hardcoded tenant-name map.
- Old contest-registration UI remains in `LandingPage.tsx` / `AuthCard.tsx`; `AdvisorDashboard.tsx` still invokes a `revoke-student` edge function that is not in this repo.
- `students.matric_no` globally unique.
- `download_transcript_bytes()` falls back to a `transcripts` bucket if `academic-slips` fails (silent fallback).
- Scanned images reach the vision model unmasked; IC protection there relies on the prompt + post-filter. Privacy-policy TODO: tell students to cover IC before scanning.
