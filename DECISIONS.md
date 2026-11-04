# SynGrad — Decisions log

The single place for **what we decided and why**. Read this before changing a feature.
**Rule:** any change to a feature, flow or rule adds or updates an entry here in the same commit
(Status, Decision, Why, Date). Never delete old entries — mark them `Replaced by #N`.

Status: **Live** (in production) · **Dev** (on dev, not merged) · **Agreed** (decided, not built) · **Proposed** (needs founder OK) · **Replaced**

---

## Accounts, emails, codes

**#1 Student signup — any email** · Proposed · 2026-11-04
- Decision: students sign up with any email; optionally verify a student email → "Verified student".
- Why: easy public launch; works after graduation and for institutions not on any domain list. Students only see their own data, so any email is safe.

**#2 Student verification unlocks cohort join + student discount** · Proposed · 2026-11-04
- Decision: verified = email domain on the *student-domain list* (built from the GWfE xlsx, student domains only; no staff/alumni). Only verified students of that institution can join a cohort; only verified students count toward confirming shared course structures.
- Why: the advisor must trust the student is really theirs.

**#3 Advisor signup — staff email, verified** · Proposed · 2026-11-04 · Replaces invite-code-only signup
- Decision: advisors sign up with a staff email and must click a verification link. Known staff domain → auto-approved. Unknown domain → "Request access", founder approves once and adds the domain.
- Why: advisors see other people's records; staff email proves they are a lecturer. Removes manual invite codes for normal cases.

**#4 Advisor invite code — backup only** · Proposed · 2026-11-04
- Decision: keep `advisor_invites` (single-use, tenant-bound, expiring) for pilots/demos/special cases.
- Why: manual override when staff-email verification can't be used.

**#5 Cohort code** · Live
- Decision: advisor creates a cohort → code; student enters it to link to that advisor and course structure version. Joining shows what the advisor will see and asks consent (consent screen: Agreed, not built).

**#6 Identity from server only** · Live
- Decision: identity always from the JWT `sub` looked up in the DB, never from browser input.

## Slip & transcript reading

**#7 Reader routing: rules → AI text → AI vision** · Dev
- Decision: text PDF + institution has a rule profile (`slip_profile`, today only UTM) + confident parse → rules; other text PDFs → one LLM call; scans → vision model.
- Why: "AI sets up, rules run it, humans approve." Rules are fast/free for high-volume institutions; AI covers the rest.

**#8 Regex profile only for high-volume institutions** · Agreed · 2026-11-04
- Why: writing rules per university doesn't scale; AI + guardrails is enough until volume justifies it.

**#9 Guardrails flag, never correct; fail loud** · Dev · 2026-11-04
- Decision: no silent defaults (missing credits/semester stay empty and are flagged; no `or 3`); unknown grade → "Needs review"; approval returns 422 on missing/invalid credits. No DB default for credits either (migration 38 drops `DEFAULT 3` on `academic_records.credits`, `courses.credits`, `template_courses.credit_hour`); the engine raises on missing credits.

**#10 Zero credits allowed only for non-CGPA grades** · Dev · 2026-11-04
- Decision: credits = 0 valid only when the grade exists in the scale and doesn't count in CGPA (e.g. PASS, HL). 
- Why: real courses like English Exit Test / industrial training have 0 credits.

**#11 IC/passport never sent to AI or stored** · Dev
- Decision: redact IC/passport text before AI; prompt forbids output; post-filter. Scans still contain IC pixels → must be disclosed in Privacy Policy; ask students to cover IC.

**#12 Slip files purged after approve AND reject** · Dev
- Decision: delete from bucket `academic-slips`; mark `[PURGED]` only when delete is confirmed.

**#13 Slip vs full transcript** · Agreed · 2026-11-04
- Decision: exam slips (UTM, UniKL) = one semester, regular upload; full transcripts (UiTM, KKTM) = one-time history import at onboarding. Same semester uploaded twice → keep one, never double-count.

**#14 AI models** · Dev · 2026-11-04
- Decision: text `LLM_MODEL=openai/gpt-oss-20b`; vision `LLM_VISION_MODEL=qwen/qwen3.8-27b` (Groq). Never Gemini free tier for student data (it may train on data).
- Why: earlier Groq models were shut down.

## Course structures

**#15 One course-structure model for advisors and single-player** · Agreed · 2026-11-01
- Decision: frozen versions per institution + programme + intake; `scope` = library / tenant / personal; edits create a new version or private copy; per-student exceptions in their own table. Detail: project doc "Unified course structure model".
- Why: avoids two systems; cohorts and single-player plug into the same data.

**#16 Grade scales per institution** · Live
- Decision: scales stored per tenant (presets + overrides), never hardcoded. Known: UTM/UiTM standard 4.00 (A- 3.67); KKTM one-decimal (A- 3.70, B+ 3.30, C+ 2.30).

**#17 Retired courses & equivalences; semester load rules** · Agreed · 2026-10-27
- Decision: never delete courses ("retired from intake X"); `course_equivalences` table; min/max credits per semester for the planner.

## Product scope & order

**#18 Build single-player mode first, then cohort integration** · Agreed · 2026-11-04
- Why: public launch without waiting for lecturer UAT.
- Order: finish & merge dev → Privacy Policy/Terms/consent → accounts & emails (#1–#4) → single-player v1 → cohort join → payments → planner.

**#19 Single-player v1 scope** · Proposed · 2026-11-04
- In: any-email signup; pick Institution → Programme → Intake from a hand-seeded list; "not listed" request form; slips or one transcript; audit + CGPA; student self-confirms.
- Out (later): handbook extraction, crowd verification, equivalences, planner.

## Infrastructure

**#20 Paid always-on backend for public launch** · Agreed · 2026-11-02 · Exception to "free tiers only"
- Decision: production Render → US$7/month instance before public launch; staging stays free.
- Why: free tier sleeps → 30–60 s first load.

**#21 Staging first, then production** · Live
- Decision: all work on `dev` → staging → merge to `main`; migrations staging first.
