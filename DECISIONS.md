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

**#23 Approval checks prerequisites from the student's template** · Dev · 2026-11-04
- Decision: finalize-approval reads prerequisites from `template_courses` (student → cohort → template). DB errors fail the approval. If the student has no template, approval still goes through with the warning "prerequisites not checked".
- Why: the old read used `course` / `course_prerequisite`. Neither table is in any migration, and errors were swallowed, so prerequisites were never checked.
- Required credits (2026-11-04): the student's own `graduation_credit_requirement` if set, else `degree_templates.total_credits_required` via the same student → cohort → template path. No fallback to 120 and no program_code guess. DB errors fail the approval. No template total → required credits 0 and the warning "credits remaining not computed".
- Why: errors were swallowed and a hard-coded 120 was used, so wrong credit totals looked real.
- Template lookup (2026-11-04): server-side only. The approval request no longer takes `cohort_id`; the template always comes from `students` (filtered by JWT `tenant_id` + `matric_no`) → cohort → template, in one helper `SupabaseService._student_template_id` (also used by progress and elective overrides). The student's graduation override is read first; the template total is read only when there is no override.
- Why: a browser-sent `cohort_id` could point the audit at another cohort's template; the same lookup was copied in four places.

**#24 Exemption checks use the real template and fail loud** · Dev · 2026-11-04
- Decision: PATCH `/students/{matric}/exemptions` checks every EX/CT course against the student's `template_courses` (via `_student_template_id`) before any write. Course not in the template → 400 "Course X is not in this student's degree template". Student with no template → 400 (cannot validate). `get_student_block_exempted_credits` raises on DB errors; (0, none) only when the student row has no values.
- Why: the old check read `degree_template_courses` and `cohorts.cohort_id` (neither exists) and swallowed the error, so any course could be exempted; the credit read hid DB errors as "no override", which silently used the template total.
- Update (2026-11-04): only `add` is checked against the template; `remove` is always allowed so stale or wrong exemptions can be cleaned up. Every item (action, EX/CT grade, credits, template for adds) is validated before any write. An `exemption_audit` insert failure now raises instead of being printed and ignored. The student is looked up inside the advisor's tenant (`tenant_id` + `matric_no`), so another tenant's student returns 404 (was 403 "cross-tenant").
- Why: the template check blocked removing exemptions saved while the old check was broken; a bad later item could fail after earlier items were written; a silent audit failure left changes with no trail.
- Update (2026-11-04): remove only selects/deletes rows with grade EX or CT; a real grade for the course is never deleted by this endpoint. Add is rejected (400 "Course X already has a grade; exemption not needed") when the student already has a non-EX/CT grade for that course; checked with the other validation, before any write. Tenant IDs are compared exactly: every `tenant_id` is a foreign key to `tenants.id` and the JWT `app_metadata.tenant_id` is copied from that DB value at registration, so no case normalization is needed.
- Why: remove deleted every row for the course code, including passed/failed attempts (breaks "data is cumulative"); an exemption next to a real grade counted the credits twice.
- Update (2026-11-05): exemptions store a real session, `SEM 1 <student's template syllabus_year>` via `normalize_semester()`; the request no longer takes a `semester`. A template year that cannot be normalized → 400. Migration 39 converts existing "Sem N" EX/CT rows the same way and fails if any row cannot be converted. Not yet applied.
- Why: `normalize_semester()` rejects "Sem N", so one exemption made every later slip approval for that student fail.
- Update (2026-11-05): add is refused if the course has any row: EX/CT → 400 "Course X already exempted — remove it first"; real grade → the 400 above. Add uses insert, not upsert, so an exemption can never replace a row. The same course twice in one request → 400. Remove with no EX/CT row → 404, checked in the validation step before any write.
- Why: with a fixed session, upsert would silently replace an existing row in that session; a remove that matched nothing still reported success and wrote an audit row.
- Update (2026-11-05): `advisee_roster_summary` counts one row per course (migration 40, not yet applied). CGPA follows `compute_cgpa`: repeat_policy picks among attempts that count in CGPA. Credits follow `compute_completed_credits`: a course counts once if any attempt is a completing pass (`is_pass` and `counts_as_completed`), so a pass followed by a later fail keeps its credits under `latest`; repeat_policy picks whose credit value is used. The old `prerequisite_met` filter on credits is removed because the engine has none. `tenant_repeat_policy()` (SECURITY DEFINER) gives the view the policy, because `tenants` has no SELECT policy.
- Why: the view summed every attempt, so retakes doubled credits and every attempt went into the CGPA; the roster disagreed with the audit.
- Known gap (2026-11-05): a student who failed a course cannot get EX/CT for it, because add is refused while any row exists. Credit transfer after a failed attempt needs its own rule (does the fail stay in CGPA?). Deferred.

## Product scope & order

**#18 Build single-player mode first, then cohort integration** · Agreed · 2026-11-04
- Why: public launch without waiting for lecturer UAT.
- Order: finish & merge dev → Privacy Policy/Terms/consent → accounts & emails (#1–#4) → single-player v1 → cohort join → payments → planner.

**#19 Single-player v1 scope** · Replaced by #22 · 2026-11-04
- In: any-email signup; pick Institution → Programme → Intake from a hand-seeded list; "not listed" request form; slips or one transcript; audit + CGPA; student self-confirms.
- Out (later): handbook extraction, crowd verification, equivalences, planner.

## Infrastructure

**#20 Paid always-on backend for public launch** · Agreed · 2026-11-02 · Exception to "free tiers only"
- Decision: production Render → US$7/month instance before public launch; staging stays free.
- Why: free tier sleeps → 30–60 s first load.

**#21 Staging first, then production** · Live
- Decision: all work on `dev` → staging → merge to `main`; migrations staging first.

**#22 v1 launch: UTM + UniKL, exam slips only, fixed time box** · Agreed (institutions) · Proposed (date) · 2026-11-04
- Decision: first public launch targets **UTM and UniKL students only**, exam slips only (no transcript import), degree audit + CGPA; "slips-only mode" (CGPA + history, no audit) for programmes not yet seeded; "not listed" → founder queue. Advisors still join via invite code (founder approves). Target launch 20 Dec 2026 (6-week box; cut scope, not the date) — date to confirm against exam calendar.
- Reading: UTM text slips → rules; UniKL text slips → AI text reader (tested OK in /lab). Scans → best effort, "Needs review" if AI fails.
- Needed for UniKL: production tenant row, real UniKL grading scale (from a slip/handbook grading key), student email domain, 1–2 seeded programmes, a few UniKL testers.
- Deferred until after first-semester review: transcript import, other institutions, staff-email advisor signup, shared course library/crowd verification, payments in code, planner.
- Why: the plan had no deadline and kept growing; two campuses with text slips keep AI cost and work small. Detail: project doc "Finishable SynGrad launch plan".

---

## Premortem 2026-11-04 (plan stress test)

Imagined failure: "6 months after public launch, SynGrad is down, gave wrong audits, or caused a privacy complaint." Causes, worst first.
**Blocks launch** = high probability × high impact; must be solved before public launch. Others are accepted risks with a mitigation.

| # | Cause | Area | Prob | Impact | Mitigation | Status |
|---|---|---|---|---|---|---|
| P1 | Free AI quota runs out on launch day (Groq free tier is roughly 200K tokens/day; a scanned transcript can use thousands) → uploads fail for everyone | Platform / free tier | High | High | Per-user upload limit (e.g. 5/day), file-hash cache, clear "busy, try later" message; move Groq to pay-as-you-go before launch | **Blocks launch** |
| P2 | Single-player students may have no matric, but records, RLS helpers and uniqueness are keyed by `(tenant_id, matric_no)` | Data model | High | High | Decide before building: key records by `student_id` (uuid), or require matric in v1 (read from the first slip, user confirms) | **Blocks launch** |
| P3 | Transcript + slip overlap is not detected because institutions name semesters differently ("SESSION 1 2021/2022", "SEM 1 2025/2026", "SEPT–JAN 2021 Semester 1") → courses double-counted, wrong CGPA | Data / overlap | High | High | One canonical semester key per institution; detect duplicates by course code + session; newer document wins with a visible warning; tests with the real samples | **Blocks launch** |
| P4 | PDPA: no account/data deletion, no retention policy, cross-border AI processing (Groq, US) not disclosed. "Data is never overwritten" conflicts with the right to delete | PDPA / Security | Medium | High | Privacy Policy + Terms + consent; "delete my account" that really deletes; define rule: cumulative while the account is active, full delete on request; disclose AI processing and that scans include IC | **Blocks launch** |
| P5 | Groq retires a model again (3 times so far) → reader fails, nobody notices | Operations | High | High | Free error alerts (email via Resend or Sentry free) on 5xx; tiny daily "model alive" check in /health; models stay in env vars; check Groq deprecations page monthly | **Blocks launch** (cheap) |
| P6 | Programme not in the hand-seeded list → most public visitors get no audit and leave | Business / Function | High | High | Launch to UTM students first; "slips-only mode" (CGPA + history without audit) for unlisted programmes; bring personal CSV/handbook upload forward | **Blocks launch** |
| P7 | Institution uses one domain for staff AND students (or alumni) → a student auto-approved as advisor creates a fake cohort and collects classmates' records | Security | Medium | High | Staff-domain list is staff-only and explicit; shared-domain institutions → manual approval; show "verified advisor at X" on the join screen | Must mitigate |
| P8 | Self-confirmed single-player grades enter an advisor cohort looking like advisor-approved data | Data / trust | High | Medium | Every record carries `verified_by` (self / advisor); advisor sees badges and re-approves on join | Must mitigate |
| P9 | Cohort code leaks (WhatsApp) → strangers join a lecturer's cohort | Security | Medium | Medium | Advisor approves join requests (or cohort cap) + matric/institution check; rate-limit code attempts | Accepted, mitigate in cohort-join phase |
| P10 | AI vision misreads a row and no printed GPA exists to catch it; student confirms without looking | Function | Medium | Medium | Force row-by-row review for `ai_scan`; later show the cropped image next to each row | Accepted |
| P11 | Student picks the wrong intake/programme (codes renamed, e.g. SECJ → SCSE) → wrong audit | Function | Medium | Medium | Infer intake from matric (UTM A24 → 2024) and first slip; "is this your programme?" confirm | Accepted |
| P12 | Resend free email limit (100/day) hit by signup + verification emails during a launch spike | Platform | Medium | Medium | Watch usage; upgrade or batch only when needed | Accepted |
| P13 | Students won't pay; university portals "good enough" | Business | High | High | Test willingness to pay early (cheap semester pass); measure semester-to-semester return rate | Accepted (business risk, not a code fix) |

Contradictions found and resolved:
- "Free tiers only" vs paid Render (#20) and P1 Groq pay-as-you-go → exceptions are logged here.
- "Data cumulative, never overwritten" vs PDPA deletion → cumulative while the account is active; real deletion on request.
