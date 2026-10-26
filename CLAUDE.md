# SynGrad (academic advising SaaS) — rules

- Work only on branch `dev`. Never checkout/merge/push `main`. Never push or run DB migrations unless I ask.
- Principles: rules first, AI only where needed; no university-specific hardcoding; identity from server-side JWT only; data is cumulative, never overwritten; fail loud, no silent fallbacks.
- Privacy (PDPA): never read, log or send IC/passport numbers to any AI; never commit slips, transcripts or .env files; staging uses test data only.
- Free tiers only: no cron, no polling, no new paid services.
- Stack: React/Vite (Vercel), FastAPI (Render), Supabase, Groq, Resend.
- Before saying done: run `py -3.12 -m pytest backend/tests -q` and `npm run build`; both must pass.
- Keep answers short; list changed files and test results.
h