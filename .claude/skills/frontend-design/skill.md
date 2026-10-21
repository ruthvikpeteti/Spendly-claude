---
name: spendly-ui
description: Designs and builds modern, production-ready UI pages and components for the Spendly expense tracker (Flask + Jinja + vanilla CSS/JS), in a clean, card-based, responsive fintech style that matches Spendly's existing look. Use this skill whenever the user asks to design, create, build, redesign or improve any page, screen, section or component for Spendly, for example "design the profile page", "create UI for the add-expense form", "build a component for category breakdown", "redesign the expenses table", or "improve the login page". Trigger even when the request is short or casual and only implies UI work in the Spendly project (dashboard, navbar, empty states, modals, budget cards, stat tiles, reports, auth pages), and even if the user does not say the word "skill".
---

# Spendly UI

Spendly is a personal expense tracker. People open it to answer quick questions: where did my money go, how much have I spent this month, what did I just spend. Good UI here makes those answers visible at a glance and makes entering an expense take seconds. The aim is a polished, minimal, fintech-style interface that looks like one product, not a pile of unrelated pages.

## Step 1: Learn the project before designing anything

Consistency beats novelty: a beautiful page that uses different colors, radii or fonts from the rest of the app looks broken. So before writing UI:

1. Read `CLAUDE.md` in the project root (architecture, tech constraints, which routes are stubs).
2. Read `templates/base.html` and `static/css/style.css`. Treat their `:root` variables and existing classes as the source of truth, because they change as the app grows. Reuse existing classes (`.btn-primary`, `.btn-ghost`, `.form-group`, `.form-input`, `.feature-card`, `.auth-card` and so on) and extend them rather than inventing parallel ones.
3. If a spec exists for the page in `.claude/specs/` (for example `04-profiles-page-design.md`), read it and follow its sections and "Definition of done".
4. If the project files are not reachable, ask the user for screenshots or the base template and CSS before designing. Do not guess the style.

### What Spendly looks like today (verify against the files, they win)
- **Mood:** warm, calm, editorial fintech. Off-white "paper" page, white cards with 1px soft borders, restrained use of color.
- **Color tokens:** `--ink`, `--ink-soft`, `--ink-muted`, `--ink-faint` for text; `--paper`, `--paper-warm`, `--paper-card` for surfaces; `--accent` (deep green) with `--accent-light`; `--accent-2` (amber) with `--accent-2-light`; `--danger` with `--danger-light`; `--border`, `--border-soft`.
- **Type:** `--font-body` (DM Sans) for UI and numbers, `--font-display` (DM Serif Display) for card and section titles.
- **Shape:** `--radius-sm` 6px (buttons, inputs), `--radius-md` 12px (cards), `--radius-lg` 20px (large panels); pill badges at 999px.
- **Layout:** `--max-width` 1200px container, 60px sticky navbar, `.main-content`, sections with generous padding, `@media (max-width: 900px)` and `600px` breakpoints.
- **Money:** Indian rupee, so show amounts as `₹1,234` with Indian digit grouping.

## Step 2: Understand the request

Inputs: the page or component name; optionally constraints, data, references. If something essential is missing, make a sensible assumption, say it in one line, and carry on instead of interrogating the user. Use realistic sample data (plausible expense names, rupee amounts, dates, categories) and keep it clearly separate from the markup so it can be swapped for real data.

## Step 3: Produce the output in this order

### 1. UI structure (brief)
- Layout: main regions and how they rearrange from desktop to mobile
- Key sections, one line each on their purpose
- Important UX decisions with the reason (for example "amount is the first, autofocused numeric field because adding an expense should take seconds")

### 2. Code
Follow the project's rules from `CLAUDE.md`, because breaking them forces the user to redo the work:
- New page means a new template that `{% extends "base.html" %}` and fills the `title`, `head`, `content` and `scripts` blocks.
- Every internal link and static file uses `url_for(...)`; never hardcode URLs.
- No inline `<style>` tags or `style=""` attributes, and no raw hex values in templates. Styles go in CSS using the existing variables. Add new tokens to `:root` only when truly needed. Page-specific styles go in their own CSS file (for example `static/css/profile.css`) linked from the `head` block; shared pieces belong in `style.css`.
- Vanilla JS only. No frameworks, jQuery, npm packages or CDN libraries, and no new pip packages. Keep page JS in the page's `scripts` block.
- Do not touch unrelated parts of other pages. Keep changes scoped to what was asked.
- Routes: UI work normally means template + CSS. Only edit `app.py` when the task asks for it (for example replacing a stub with a view that passes hardcoded sample data, as the specs describe). Never implement a stub route's real logic unless the task targets that step, and never put DB logic in routes.
- Code quality: clean CSS with variables, small reusable classes or Jinja macros/partials (stat tile, card, badge, table row, form field) instead of one-offs, semantic HTML, labelled inputs, visible focus states, minimal boilerplate.
- Responsive from 360px phones up to wide desktops, using the existing breakpoints.
- Deliver longer code as files in the right folders and say where each goes, rather than pasting a wall of code.

### 3. Icons
Use Lucide-style icons wherever an icon adds meaning: categories (utensils, car, house, shopping-bag, heart-pulse, film), actions (plus, pencil, trash-2), trends (trending-up, trending-down), empty states. Because the project allows no CDN libraries, inline the SVGs: `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="2"`, round caps and joins, `aria-hidden="true"`, sized and colored from CSS. If an icon repeats in several places, make it a Jinja macro. Keep a text label on important actions; icons support text, they do not replace it.

## Design rules

- **Look:** minimal, clean, card-based. Rounded corners, soft shadows (subtle, e.g. `0 1px 2px` plus a gentle larger blur at low opacity, defined once as a variable), subtle colors. Spendly's existing cards lean on 1px borders, so keep shadows quiet and let borders and surfaces do most of the work.
- **Spacing:** 8px grid (4px only for tight inner gaps), written as rem multiples of 0.5. Generous space between sections, consistent padding inside cards.
- **Hierarchy:** one primary action per view. Big, confident figures for key numbers (total spent, budget left); quiet muted text for labels and metadata; display serif only for titles.
- **Money and data:** tabular numerals (`font-variant-numeric: tabular-nums`) so amounts align; right-align amount columns; convey up/down or over-budget with color plus an icon or text, never color alone; category badges via CSS classes (for example `.badge-food`), not inline colors.
- **States:** include empty, error and (where relevant) loading states for lists, tables and charts.
- **Interaction:** subtle 150-200ms hover and focus transitions, clear affordances, typed inputs (number, date, select), inline validation messages, and a pattern like the existing `.auth-error` for errors.
- **Accessibility:** sufficient contrast, labels for every input, keyboard reachable controls, a table that becomes cards or scrolls sensibly on mobile.
- **Avoid:** generic or dated UI (heavy borders, harsh shadows, default browser form controls, rainbow palettes), clutter, random one-off styles, mixed radii, new fonts or colors that fight the existing palette, and unstructured code dumps with no explanation of how the pieces fit.

## Final check before replying
- Did I read the project's CSS and reuse its tokens and classes?
- Does the template extend `base.html`, use `url_for`, and avoid inline styles, raw hex values and external JS/CSS libraries?
- Is spacing on the 8px grid, and does the layout hold up at phone width?
- Are empty and error states handled, and is the sample data clearly marked as sample?
- Is the reply ordered as UI structure, then code, then icon notes?