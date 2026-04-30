# Whitelabel Catalog Tools — Partner Portal

Brand-agnostic, file-based version of the HeyRoya metadata workflow. Single-file static HTML, no build step.

## What's here so far

- `pages/index.html` — landing
- `pages/how-it-works.html` — six-step workflow detail (per-step Partner / End-client / {{PartnerBrand}} role boxes, file formats, timing)
- `pages/pricing.html` — three-tier wholesale model (Starter / Standard / Volume) + comparison table + scan/work/case definitions + billing terms
- `pages/faq.html` — 15 Q&A in 4 categories, native `<details>` accordion
- `pages/contact.html` — contact cards + mailto-only form (no backend, no data collection)
- `brand.config.json` — placeholder values + theme tokens for one partner
- `about.txt` / `plan.txt` — original product + engineering specs (do not modify)

All pages: bilingual EN/SV via `data-i18n` + inline `TRANSLATIONS` dict. Theme tokens as CSS variables in each page's `:root`. Single-file, inline CSS+JS, no build, no external libraries.

Future: `pages/{partner, terms}.html`, client-side `tools/{scan, apply}.html` with a configurable rules file, and the deliverable templates from `about.txt` under `templates/` (health-report, worksheet XLSX spec, CWR/CSV exports, partner instructions, onboarding kit, reseller docs, disclaimer pack).

## To preview the landing page

Just open `pages/index.html` in a browser — no server needed. Toggle EN/SV with the language switch in the nav. Lang preference persists in `localStorage`.

## To rebrand for a partner

There is no build step on purpose. To produce a partner-specific copy:

1. Copy this folder to a new directory (e.g. `partners/acme/`).
2. Edit `brand.config.json` for reference.
3. Run a literal find/replace across the new folder's HTML:
   - `{{PartnerBrand}}` → partner's display name
   - `{{PartnerContact}}` → partner's contact email
   - `{{PartnerDomain}}` → partner's domain
4. To rebrand colors, search-replace the hex values in the `:root` block of each HTML file (the values match `theme_tokens` in `brand.config.json`).
5. To translate beyond EN/SV, add a new language to the `TRANSLATIONS` object at the bottom of each HTML file and add a button to `.lang-toggle` in the nav.

## Strict rules (from `plan.txt` and `about.txt`)

- Do **not** modify `roya-demo/frontend/` or `roya-demo/docs/` (the live HeyRoya site).
- Do **not** deploy or push to GitHub without explicit OK.
- Single-file pattern: each page is self-contained — inline CSS + JS, no external bundles.
- Tone: Scandinavian enterprise — short, factual, metadata-only, zero-trust. No marketing adjectives, no royalty/financial claims, no system-access implications.

## Live demo link

The "Live demo →" link in the nav currently points at the HeyRoya demo (`heyroya.se/pages/review.html?demo=1`). For a true partner deployment this should be replaced with the partner's own demo URL — note in `brand.config.json` under `demo_link`.

## Internal-tool gate password

The HeyRoya demo is gated by `heyroya2026` (entered once per browser session). Partners running the live demo before deploying their own version will need this password.
