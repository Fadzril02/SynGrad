# SynGrad (academic advising SaaS) — rules

- Product: PRD.md · System: Architecture.md · UI: DesignSystem.md — read the relevant one before changing that area.
- Work only on branch `dev`. Never checkout/merge/push `main`. Never push or run DB migrations unless I ask.
- Principles: rules first, AI only where needed; no university-specific hardcoding; identity from server-side JWT only; data is cumulative, never overwritten; fail loud, no silent fallbacks.
- Privacy (PDPA): never read, log or send IC/passport numbers to any AI; never commit slips, transcripts or .env files; staging uses test data only.
- Free tiers only: no cron, no polling, no new paid services.
- No faculty/department layer: advisor ↔ student only.
- Schema changes only via a new numbered migration (never edit an applied one); staging before prod.
- New table: RLS on, policies via `my_*()` helpers, anon gets nothing; views use `security_invoker = true`.
- New endpoint: JWT dependency; identity from JWT `sub` → DB; document access via `_load_authorized_document()`. Browser never writes status, results, identity columns or other users' rows.
- Student edits to AI-read values keep the original (`ai_grade`/`ai_course_code`, `is_altered`); never overwrite it in place.
- Verify "fixed in code" separately from "live in production".
- Stack: React/Vite (Vercel), FastAPI (Render), Supabase, Groq, Resend.
- Before saying done: run `py -3.12 -m pytest backend/tests -q` and `npm run build`; both must pass.
- Standards detail: Essentials.md
- Keep answers short; list changed files and test results.
- Skills: ponytail for every change; /ponytail-review before commit; verification-before-completion before saying done; diagnosing-bugs for errors; test-driven-development for engine logic; frontend-design + DesignSystem.md for UI; code-review + deploy-checklist before merging to main.
