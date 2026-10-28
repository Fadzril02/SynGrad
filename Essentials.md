# SynGrad • Engineering Standards & Core Principles (Essentials)
## The Non-Negotiable Rules of the SynGrad Codebase

---

### Document Information
* **Document:** SynGrad Engineering Charter & Coding Standards
* **Author:** Principal Staff Engineer & Technical Architecture Team
* **Scope:** All Frontend (React/TypeScript), Backend (Python/FastAPI), and Database (PostgreSQL/Supabase) Contributions
* **Status:** Mandatory Repository Policy
* **Version:** 1.0.0

---

## 0. Working Rules (current, 2026-10-28) — read this first

CLAUDE.md holds the binding short rules; this file is the detail. These five override anything below that conflicts.

1. **Zero-Waste pipeline.** Deterministic regex first. LLM (Groq) only for lines regex can't parse.
2. **Multi-university.** Never hardcode matric format, email domain, grading scale, course codes or session formats in code or CHECK constraints. Read from `tenants`, `grade_scales`, templates.
3. **Server-side identity only.** `advisor_id`, `tenant_id`, `matric_no`, document status and extraction results are decided by the backend/DB from the verified JWT. Never trust a request body or a browser write for them.
4. **Cumulative, never overwrite.** Semester history accumulates; each attempt is its own row.
5. **Fail loud.** No silent defaults, no guessing (e.g. semester `|| 1`). Unknown → error or warning shown to the user.

Also:
- Schema changes only via a new numbered migration. Never edit an applied one. Apply to staging first (from mig 30 on), then prod.
- Free tiers only (Supabase, Render, Vercel, Resend). No cron, no polling, no new paid service.
- No faculty layer. Advisor ↔ student only.
- Verify "fixed in code" separately from "live in production".
- UI palette: original SynGrad blue `blue-900` (users preferred it). Tailwind custom grey is `ink`, not `slate`. Full tokens: DesignSystem.md.

---

## 1. The Four Pillar Principles

Every pull request, architectural decision, and line of code committed to this repository must strictly adhere to the following four immutable engineering pillars:

```
┌───────────────────────────────────────────────────────────────────────────┐
│                      THE FOUR PILLARS OF SYNGRAD                          │
├─────────────────────────────────────┬─────────────────────────────────────┤
│ 1. ACADEMIC MINIMALISM (UI/UX)      │ 2. DATA INTEGRITY OVER UX           │
│ Clean institutional utility. Blue-  │ Hard database constraints govern.   │
│ 900 & white palette. Zero fluff.    │ Never silently fail or default.     │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ 3. ZERO-TRUST CLIENT                │ 4. VARIABLE-DRIVEN RENDERING        │
│ The frontend is compromised. Audit  │ No hardcoded fallbacks. Everything  │
│ provenance & cross-check JWTs.      │ inherits dynamically from blueprints│
└─────────────────────────────────────┴─────────────────────────────────────┘
```

---

## 2. Pillar 1: UI/UX Standard — "Academic Minimalist"

SynGrad is an institutional academic advising platform, not an entertainment app, marketing website, or generic venture-funded SaaS product. Its visual design must command institutional authority, clarity, and utilitarian density.

### 2.1 The Palette (source of truth: DesignSystem.md)
* **Primary:** `bg-blue-900` (`#1E3A8A`), hover `bg-blue-800`; `text-blue-900`, `border-blue-900`.
* **Legacy maroon/gold** (`#990033` / `#FFCC00`, old UTM branding) survives in the legacy `Button`, `CardTitle`, `AppLayout`. Don't use it in new UI.
* **Functional State Colors:**
  * **Critical Error / Forgery:** `bg-rose-50`, `border-rose-200`, `text-rose-700` (Never neon red).
  * **Verified / Active:** `bg-emerald-50`, `border-emerald-200`, `text-emerald-700`.
  * **Pending Audit / Warning:** `bg-amber-50`, `border-amber-200`, `text-amber-800`.
* **Neutral Canvas:** Clean white cards (`bg-white`), neutral page canvas (`bg-[#F9FAFB]`), subtle hair-thin borders (`border-gray-200`).

### 2.2 Prohibited Aesthetics (Strictly Enforced)
* ❌ **No Playful Gradients or Mesh Blobs:** Avoid rainbow background gradients, animated pastel blobs, and purple/pink neon glow effects.
* ❌ **No Generic SaaS "Bubble" Aesthetics:** Avoid giant pill-shaped buttons with massive box shadows, floating decorative elements, and excessive border radiuses (`rounded-3xl` or `rounded-full` on cards).
* ❌ **No Uninformative Placeholders:** Never use placeholder images or unstyled mock text. If tabular data is loading, display a clean institutional skeleton loader or spinner.

### 2.3 Required Design Patterns
* ✅ **High Information Density:** Dense tables with clear column headers, monospace font for codes (`font-mono`), and compact badges.
* ✅ **Explicit System Feedback:** Use Sonner toasts (`toast.success()`, `toast.error()`) alongside persistent in-form alert banners for all state transitions.
* ✅ **State-Responsive Button Hierarchy:** Main submit buttons must visibly indicate disabled states (`disabled:opacity-50 disabled:cursor-not-allowed`) and display an inline `Loader2` spinner during active network transactions.

---

## 3. Pillar 2: Data Integrity Over UX (Fail Fast & Hard Constraints)

In academic record management, **a clean error message is infinitely better than corrupted data**. The frontend must never silently swallow an error, create mock fallback records, or bypass database validation.

### 3.1 Hard Database Constraints Govern
* Frontend form validation is an ergonomic convenience; the PostgreSQL database schema is the sole authoritative source of truth.
* Primary keys and CHECK constraints must never be loosened to accommodate unvalidated client requests, but they must stay university-neutral: no tenant-specific formats in CHECKs (e.g. the matric check is the generic `^[A-Z0-9]{5,15}$` since migration 09; per-tenant formats live in `tenants`).

### 3.2 Strict Prohibition of Silent Fallbacks
* **No Default UUIDs:** If a request payload is missing an entity ID (e.g., `template_id`, `cohort_id`, or `advisor_staff_id`), the server must reject the call with HTTP `422 Unprocessable Entity`. Generating a random UUID (`uuid4()`) as a fallback is strictly prohibited.
* **No Fake Academic Records:** If a course code cannot be extracted from a transcript, it must be flagged for human review (`processing_status = 'Pending_Advisor_Approval'`), never synthesized or guessed.
* **Ruthless Cache Invalidation:** Sign-out must wipe local state unconditionally, whatever the server says. `signOut` in [`AuthContext.tsx`](src/context/AuthContext.tsx) first clears all `localStorage`, `sessionStorage` and cookies, resets React auth state, and only then calls `supabase.auth.signOut()` (a server failure is logged, not blocking).

---

## 4. Pillar 3: Zero-Trust Client Architecture

The frontend client operates in an untrusted user environment. All student submissions, grade claims, and identity assertions must be treated as potentially malicious or altered.

### 4.1 Provenance Tracking & The Tamper Trap
* When students review OCR-extracted records in the verification modal, direct edits to course codes or grades must **never overwrite the extracted ground truth in place**.
* The handler `handleStagedDataChange` in [`StudentPortal.tsx`](src/app/pages/student/StudentPortal.tsx) must immediately preserve original AI values and flag the record:

```typescript
// MANDATORY PROVENANCE LOCK
if (!newData.courses[index].ai_grade && field === "grade") {
  newData.courses[index].ai_grade = newData.courses[index].grade;
}
if (!newData.courses[index].ai_course_code && field === "course_code") {
  newData.courses[index].ai_course_code = newData.courses[index].course_code;
}

newData.courses[index].is_altered = true;
newData.courses[index][field] = value.toUpperCase();
```

* In the Advisor's [`CorrectionsQueue.tsx`](src/app/pages/advisor/CorrectionsQueue.tsx), a document with `fraud_flag` shows a high-contrast alert next to the original document.

### 4.2 Backend JWT Cross-Referencing
* The FastAPI backend never trusts identity claims passed in JSON request bodies.
* Every `/audit/*` mutation (`/extract`, `/finalize-approval`, `/reject-document`, `/purge-document`, `/submit-verification`) depends on [`verify_advisor_jwt`](backend/app/core/auth.py), which verifies the ES256 JWT via the Supabase JWKS. The caller is resolved from the JWT `sub` against `advisors.user_id` / `students.user_id`, and document access goes through `_load_authorized_document()`.
* A caller who doesn't own the record gets HTTP `403 Forbidden`.

---

## 5. Pillar 4: Variable-Driven Rendering (No Hardcoded Fallbacks)

SynGrad is a multi-tenant blueprint engine designed to support multiple faculties, syllabus years, and universities without codebase modifications.

### 5.1 The Rule of Zero Hardcoded Curricula
* **Prohibited Code Patterns:**
  ```typescript
  // ❌ STRICTLY FORBIDDEN:
  const program = student.program || "SECJ";
  const syllabus = student.syllabus || "2024/2025";
  const uni = "Universiti Teknologi Malaysia";
  ```
* **Required Code Patterns:**
  * All degree codes, program titles, syllabus years, and required credit hours must be dynamically derived from the `degree_templates` SQL join:
  ```typescript
  // ✅ MANDATORY DYNAMIC RESOLUTION:
  const tmpl = Array.isArray(cohort.degree_templates) 
    ? cohort.degree_templates[0] 
    : cohort.degree_templates;
  const programCode = tmpl?.program_code;
  const syllabusYear = tmpl?.syllabus_year;
  const programName = tmpl?.program_name;
  
  if (!programCode || !syllabusYear) {
    throw new Error("Corrupted cohort: missing linked degree blueprint.");
  }
  ```

### 5.2 Dynamic Form Configuration
* The student registration form must never offer dropdowns for syllabus versions. By validating the advisor's `cohort_code`, the system automatically resolves the linked `degree_templates` row and injects the proper blueprint keys into the student's record.

---

## 6. Codebase Map (current)

```
backend/app/
  core/        auth.py (JWKS ES256), config.py (settings, CORS regex), supabase_client.py
  engine/      extractor.py, parsers/malaysian_regex.py (slip regex), parsers/csv_course_parser.py,
               grading.py (tenant grade scale, repeat policy), graph_resolver.py (prereqs),
               llm_fallback.py (Groq, unparsed lines only), progress.py, slip_pipeline.py,
               slip_validation.py, universal_reader.py, scanned_reader.py
  schemas/     audit.py, course.py
  v1/endpoints/ audit.py, register.py, courses.py, advising.py, students.py, health.py, lab.py
backend/tests/ pytest; conftest stubs _load_authorized_document unless marked real_doc_auth

src/
  app/routes.tsx, app/App.tsx
  app/pages/landing/*        landing sections (FoundingAdvisorCallout.tsx is unused)
  app/pages/student/*        StudentPortal (upload + verify), StudentUploadSlip, DegreeAuditView,
                             AcademicHistoryView, AdvisingNotesView, CgpaCalculatorView, StudentDashboardView
  app/pages/advisor/*        AdvisorPortal/Layout, AdvisorDashboard, CorrectionsQueue, StudentsList, StudentView,
                             CurriculumTemplatesView
  app/pages/lab/SlipLab.tsx  slip extraction lab
  pages/auth/*               StudentAuth, AdvisorLogin, CompleteRegistration
  context/AuthContext.tsx    profile fetch deferred with setTimeout inside onAuthStateChange
  lib/api.ts                 backend client (Bearer token); lib/gradeScale.ts; lib/tenants.ts; lib/supabase.ts; lib/semester.ts

supabase/migrations/         NN_name.sql, current head = 36
```

---

## 7. Pre-merge Checklist

* [ ] `npm run build` clean; `py -3.12 -m pytest backend/tests -q` green (178+).
* [ ] No university constants: grep for `UTM`, `graduate.utm.my`, `SECJ`, `SCS`, matric regex literals, `'2024/2025'`, `|| 1`.
* [ ] New table: RLS enabled + policies using the `my_*()` helpers; anon gets nothing; views use `security_invoker = true`.
* [ ] New endpoint: JWT dependency; identity from JWT/DB; document access via `_load_authorized_document()`.
* [ ] Browser never writes status, results, identity columns or other users' rows.
* [ ] Migration added (not edited), with verify queries and rollback; applied to staging before prod.
* [ ] No new paid service, cron or polling.
* [ ] Tested live after deploy (not just locally); tag the milestone.
