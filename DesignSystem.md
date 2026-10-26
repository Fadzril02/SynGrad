# SynGrad — Design System

Describes the UI **as the code is today** (2026-10-26), not an aspiration. Sources: `tailwind.config.js`, `src/index.css`, `src/app/components/`, `src/components/shared/`, and the class usage across `src/**/*.tsx`. Tailwind v3, icons `lucide-react`, toasts `sonner`.

## 1. Colour

What pages actually use is plain Tailwind palette classes. The custom theme tokens exist but are almost unused (see §8).

| Role | Use | Classes in use |
|---|---|---|
| Brand / primary action | buttons, active nav, headings accent | `bg-blue-900` (= `#1E3A8A`), hover `bg-blue-800` / `#1E40AF`; text `text-blue-900` |
| Page background | app shells | `bg-[#F9FAFB]` (= gray-50) |
| Surface | cards, sidebar, modals | `bg-white` + `border border-gray-200` |
| Subtle surface | table heads, hover rows | `bg-gray-50`, `bg-gray-100` |
| Text | primary / body / secondary / muted | `text-gray-900` / `text-gray-700` / `text-gray-500`–`600` / `text-gray-400` |
| Info | AI-read notices, neutral highlights | `bg-blue-50 border-blue-200 text-blue-900` |
| Success | passed, approved | `bg-emerald-50 border-emerald-200 text-emerald-700` |
| Warning | guardrail warnings | `bg-amber-50 border-amber-200/300 text-amber-800/900`, icon `text-amber-600` |
| Danger | errors, blocking warnings, reject | `bg-rose-50 border-rose-200/300 text-rose-700/900`, icon `text-rose-600` |
| Legacy maroon / gold | old UTM branding (legacy `Button`, some advisor pages) | `#990033`, `#FFCC00` |
| Landing body text | landing pages only | `text-ink` (`#334155`) |

Use rose (not red) for danger and emerald (not green) for success — that is the majority usage.

## 2. Typography
- Fonts (Google Fonts in `index.html`): **Inter** = `font-sans` (default), **Source Serif 4** = `font-serif` (landing/display headings only, ~7 files).
- `font-mono` is used heavily (course codes, matric numbers, grades, IDs).
- Scale in practice: `text-xs` is the workhorse (labels, tables, banners), `text-sm` body, `text-lg`–`text-2xl` page/section titles, `text-3xl`+ landing only.
- Weights: `font-medium` (labels, buttons), `font-semibold`/`font-bold` (titles, table emphasis), `font-extrabold` (logo wordmark).
- Small caps label pattern: `text-xs uppercase tracking-wider text-gray-500 font-semibold`.

## 3. Spacing
Tailwind default scale. Common: card padding `p-6` (dense: `p-4`), horizontal `px-4`/`px-6`, control height `py-2`–`py-2.5`, gaps `gap-1.5`/`gap-2`/`gap-3`, banner padding `p-3`–`p-3.5`.

## 4. Radius & elevation
- `--radius: 0.625rem` → Tailwind `rounded-lg` / `md` / `sm` are remapped to 10 / 8 / 6 px.
- Usage: `rounded-lg` controls, banners, nav items · `rounded-xl` cards · `rounded-2xl` large panels/landing · `rounded-full` pills, badges, avatars, switch.
- Shadow: `shadow-sm` on cards and logo tiles; nothing heavier in app pages.

## 5. Components

Import from `src/app/components/ui` (resolves to **`ui.tsx`**, see §8). Pages import it as `../../components/ui`.

| Component | Variants | Use |
|---|---|---|
| `Button` (`ui.tsx`) | `primary` (maroon, default), `secondary`, `outline`, `ghost`, `accent` (gold), `danger`, `success`; sizes `default`/`sm`/`lg`/`icon` | All actions. Many newer pages instead write raw `bg-blue-900` buttons. |
| `Card`, `CardHeader`, `CardTitle`, `CardContent` (`ui.tsx`) | — | Grouped content blocks: white, `rounded-xl`, gray border, `shadow-sm`. |
| `Badge` (`ui.tsx`) | `default`, `warning`, `success`, `danger`, `outline` | Status pills (`rounded-full`). |
| `Input`, `Label` (`ui.tsx`) | — | Form fields. |
| `Switch` (`ui/switch.tsx`) | — | Binary toggles (cohort lock). |
| `Toaster` (`ui/sonner.tsx`) | — | Mounted once in `App.tsx`: top-right, rich colours, close button. |
| `CourseLedger` (`components/shared`) | — | Course record tables (advisor StudentView, student DegreeAuditView). |
| `TrafficLightGrid` (`components/advisor`) | — | Advisee risk grid on AdvisorDashboard. |
| `LoadingScreen`, `ErrorBoundary` (`components/shared`) | — | Full-page loading; app-level error catch in `main.tsx`. |
| Layouts | `AdvisorLayout.tsx`; student shell inside `StudentPortal.tsx` | White sidebar (`w-72` advisor, `w-64` student), `border-r border-gray-200`, slide-in on mobile. |

## 6. Notices & feedback

| Pattern | When | How |
|---|---|---|
| `toast.success` / `toast.error` (sonner) | Result of a user action (upload parsed, submitted, saved, failed) | One short sentence. Prefer the server's `detail` for errors. |
| Persistent toast `server-waking` | Backend cold start | Automatic in `src/lib/api.ts`; never call it from pages. |
| Inline banner (info) | AI-read slip | `p-3.5 rounded-lg border bg-blue-50 border-blue-200 text-blue-900 text-xs font-medium flex items-center` + `Sparkles` icon. Texts: "Read by AI — please check every row carefully" / "Read from a scanned slip by AI — scans can be misread, please check every row carefully." |
| Inline banner (warning / blocking) | Guardrail warnings above the slip table | amber for warnings, rose for blocking (matric mismatch), `AlertTriangle` icon, bold title line + message. |
| `window.confirm` | Destructive actions (delete cohort, reject slip, revoke) | Current practice; no confirm dialog component exists. |

## 7. Rules of thumb (from current majority usage)
- Brand = blue-900; gray neutrals; status colours via rose / amber / emerald / blue 50-200-700/900 triplets.
- Course codes, matrics, grades in `font-mono`.
- New UI: reuse `ui.tsx` components and the banner patterns above rather than inventing new ones.

## 8. Inconsistencies found (not fixed)
1. **Two component libraries.** `src/app/components/ui.tsx` and the folder `src/app/components/ui/` both export `Button`, `Card`, `Badge`, `Input`, `Label`. Imports of `.../components/ui` resolve to `ui.tsx`; the folder's versions are unused (only `switch` and `sonner` are imported directly).
2. **Two brand colours.** Legacy `Button` primary, `CardTitle`, `AppLayout` use maroon `#990033` / gold `#FFCC00` (UTM); most pages use blue-900. `#1E3A8A` is written both as a hex literal (~100×) and as `blue-900`.
3. **Unused theme tokens.** `tailwind.config.js` defines `navy`, `maroon`, `ivory`, `gold`, `accent-blue`, `surface`, `text-primary`, `status-*` etc.; none are used in `.tsx` (only `ink` is, on landing pages). `--utm-maroon`/`--utm-gold` vars unused.
4. **Dead stylesheet set.** `src/styles/{index,theme,tailwind,fonts,globals}.css` are never imported (Tailwind v4 syntax, different `--primary`, dark theme); `src/index.css` is the live one.
5. **Broken class.** Folder `Input` uses `bg-input-background`, which has no Tailwind colour mapping.
6. **Mixed neutrals.** `gray-*` (23 files) and `slate-*` (12 files) both used for the same roles.
7. **Mixed status hues.** rose vs red, emerald vs green, amber vs yellow appear for the same meaning.
8. **Feedback styles.** `alert()` is still used for errors in `AdvisorDashboard.tsx` and `CorrectionsQueue.tsx` alongside sonner toasts.
9. **Stale branding.** `LoadingScreen` shows "INITIALIZING L.U.M.A. SECURE CONTEXT..." on a dark slate/indigo screen; `AppLayout` shows "SE Smart AA". `AppLayout`, `CorrectionModal`, `GradePredictor`, `figma/ImageWithFallback` are not used by any route.
10. **Switch bug.** `ui/switch.tsx` spreads `{...props}` after its own `onClick`, so a caller-supplied `onClick` replaces the handler and `onCheckedChange` stops firing. Its colours (`bg-rose-600` on, `ring-blue-900`) also don't match either brand colour.
11. **Sidebar width** differs: advisor `w-72`, student `w-64`.
12. **Dark mode.** `@custom-variant dark` and `dark:` classes exist in components, but no dark tokens are defined in the live `index.css`.
