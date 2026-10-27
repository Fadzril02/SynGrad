# SynGrad — Product Requirements (PRD)

Multi-tenant academic advising SaaS. Updated 2026-10-26. How it is built: `Architecture.md`. UI rules: `DesignSystem.md`.

## 1. Product

Advisors and their students replace paper result slips and spreadsheet degree audits with one shared record:

1. Advisor creates a **cohort** bound to a degree template; students self-register with the cohort code.
2. Student uploads a **result slip** (PDF). The system reads it (rules first, AI only when rules can't), the student checks every row and submits.
3. Advisor reviews the submission next to the original slip, then **approves** (rows written to the student's record) or **rejects**. The slip file is deleted either way.
4. Both see **degree progress** (credits, CGPA, required / elective courses) computed from the tenant's own grading scale and curriculum.

Principles: rules first, AI only where needed; nothing university-specific in code; identity from the server-side JWT only; records are cumulative (each attempt is kept, never overwritten); fail loud, no silent fallbacks.

## 2. Users

| Role | Can |
|---|---|
| **Student** | Register with cohort code + matric + institutional email; upload slips; review/edit extracted rows; view academic history, degree audit, CGPA calculator, advising notes. |
| **Advisor** | Register with an invite code; create/lock cohorts; upload and edit curriculum templates (owner only); review/approve/reject slips; manage exemptions and elective overrides; write advising notes and email the student a notification. |
| **Staging staff** | Use the Slip Lab (`/lab`) to test slip reading. Staging only, allow-listed emails. |

No faculty/department layer: advisor ↔ student only. Founding advisors (`advisors.is_founding_advisor`) get free access.

## 3. Features

### 3.1 Registration
- Students: cohort code must exist and be unlocked; email domain must be one of the tenant's `student_email_domains` (a tenant may have several); matric must match the tenant's `matric_regex`; duplicate matric in the tenant → 409.
- Advisors: invite code (`advisor_invites`).

### 3.2 Slip reading
- **Text PDF, tenant has a rules profile** (`slip_profile = 'utm'`): deterministic parser. Used only if confident (semester + session found, ≥1 course, no unparsed lines). `source = 'rules'`.
- **Otherwise text PDF**: one AI call (universal reader). `source = 'ai'`. UI banner: "Read by AI — please check every row carefully".
- **Scanned PDF (no text layer)**: pages rendered to images and read by a vision model (`LLM_VISION_MODEL`, currently `qwen/qwen3.8-27b`). Max 6 pages. `source = 'ai_scan'`. UI banner: "Read from a scanned slip by AI — scans can be misread, please check every row carefully." If no vision model is configured, the upload is refused with a clear message.
- **Guardrails** run on every result and only add warnings, never change values: grade in tenant scale, credits > 0, course-code sanity, semester format, printed vs recomputed GPA, slip matric vs student matric (mismatch blocks submission: "This slip may belong to someone else").
- **Tamper evidence**: the server keeps the originally extracted rows and computes `is_altered` itself on submit; PDF metadata from editing tools sets `fraud_flag`. Advisors see both.
- Multi-semester transcripts keep each course's own semester.

### 3.3 Privacy (PDPA)
- IC/NRIC/passport numbers are masked in slip text **before** it is sent to AI. AI output is filtered so an IC is never stored (not as matric, name or code).
- Scanned page images live in memory only; never stored.
- The slip file is deleted from storage after advisor **approve or reject**.
- Students should cover their IC before scanning (privacy-policy TODO; a scanned image cannot be masked before the AI sees it).

### 3.4 Progress & records
- One `academic_records` row per attempt; the tenant `repeat_policy` decides which attempt counts.
- Elective slots, manual elective assign/exclude, exemptions.
- Curriculum via CSV template upload and in-app template editor (owner only).

### 3.5 Advising notes
- Advisor notes visible to the student. "Notify" emails the student (no note text in the email), max 1 per student per hour.

### 3.6 Cold start
- Backend runs on Render free tier and sleeps when idle. The landing and complete-registration pages send one silent warm-up ping per page load. Any API call pending > 5 s shows one toast: "Waking up the server — first load can take up to a minute." It hides when the last slow call finishes.

## 4. Non-functional

| Area | Requirement |
|---|---|
| Identity | Backend verifies Supabase ES256 JWTs via JWKS (1 h cache). User/tenant/matric never taken from the request body. |
| Isolation | RLS on every table; advisors see only their advisees; students only themselves. |
| Cost | Free tiers only: Supabase, Render, Vercel, Groq, Resend. No cron, no polling. |
| Startup | Heavy libraries (PyMuPDF, OpenAI SDK) load on first use, not at app import. |

## 5. Business model & roadmap (2026-10-01)

### 5.1 Goal
Passive-income subscription SaaS sold to **individual advisors** (B2B2C: advisor pays, their students use it free).

### 5.2 Plans
| Plan | Who | Price | Notes |
|---|---|---|---|
| Founding | UAT pilot advisors | Free forever | `advisors.is_founding_advisor = true`; set by SQL cut-off date before launch |
| Free | Any advisor | Free | Limited (student cap, TBD) |
| Pro | Any advisor | Paid (Stripe) | Higher/no limits |

Constraint until revenue: stay on free tiers. No cron/polling.

### 5.3 Roadmap
| # | Milestone | Status |
|---|---|---|
| 1 | Curriculum upload (CSV template) | Done |
| 2 | Elective slots | Done |
| 3 | Tenant grading scale + multi-attempt records | Done |
| — | Advising notes + email notify; upload security (migs 29–30) | Done / 30 pending apply |
| 4 | Template editor + manual elective override | Done (migs 33–34) |
| — | Universal slip reader, scanned slips, Slip Lab, IC redaction, purge on reject, cold-start notice | Done |
| 5 | Staging tests | Next |
| 6 | Merge `dev` → `main` | |
| 7 | Week 2: PDPA privacy policy + consent; multi-institution blockers | |
| 8 | Single-player phases 1–4 (see Architecture "Planned") | |
| 9 | Payments (plans & limits, billing) | |
| 10 | Semester planner | |

Full pre-launch list: project doc `claude/launch-checklist.md`.

### 5.4 Pilot
- Tenant `UTM`: matric `^[A-Z][0-9]{2}[A-Z]{2}[0-9]{4}$`, student domain `graduate.utm.my`, min pass `D+`, default prereq min `C`, repeat policy `latest`, `slip_profile = 'utm'`.
- UAT feedback via questionnaire (`src/config/product.ts`); founding flag left on for all UAT advisors.
