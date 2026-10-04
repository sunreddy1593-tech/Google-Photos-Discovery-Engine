---
name: Photo Discovery Lab
colors:
  surface: '#faf9f5'
  surface-dim: '#dbdad6'
  surface-bright: '#faf9f5'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f4f0'
  surface-container: '#efeeea'
  surface-container-high: '#e9e8e4'
  surface-container-highest: '#e3e2df'
  on-surface: '#1b1c1a'
  on-surface-variant: '#3d4947'
  inverse-surface: '#30312e'
  inverse-on-surface: '#f2f1ed'
  outline: '#6d7a77'
  outline-variant: '#bcc9c6'
  surface-tint: '#006a61'
  primary: '#00685f'
  on-primary: '#ffffff'
  primary-container: '#008378'
  on-primary-container: '#f4fffc'
  inverse-primary: '#6bd8cb'
  secondary: '#545f73'
  on-secondary: '#ffffff'
  secondary-container: '#d5e0f8'
  on-secondary-container: '#586377'
  tertiary: '#4648d4'
  on-tertiary: '#ffffff'
  tertiary-container: '#6063ee'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#89f5e7'
  primary-fixed-dim: '#6bd8cb'
  on-primary-fixed: '#00201d'
  on-primary-fixed-variant: '#005049'
  secondary-fixed: '#d8e3fb'
  secondary-fixed-dim: '#bcc7de'
  on-secondary-fixed: '#111c2d'
  on-secondary-fixed-variant: '#3c475a'
  tertiary-fixed: '#e1e0ff'
  tertiary-fixed-dim: '#c0c1ff'
  on-tertiary-fixed: '#07006c'
  on-tertiary-fixed-variant: '#2f2ebe'
  background: '#faf9f5'
  on-background: '#1b1c1a'
  surface-variant: '#e3e2df'
typography:
  headline-xl:
    fontFamily: Plus Jakarta Sans
    fontSize: 2rem
    fontWeight: '700'
    lineHeight: 2.5rem
    letterSpacing: -0.025em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 1.5rem
    fontWeight: '600'
    lineHeight: 2rem
    letterSpacing: -0.02em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 1.125rem
    fontWeight: '600'
    lineHeight: 1.625rem
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: '400'
    lineHeight: 1.625rem
  body-md:
    fontFamily: Inter
    fontSize: 0.875rem
    fontWeight: '400'
    lineHeight: 1.375rem
  body-sm:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: '400'
    lineHeight: 1.125rem
  metric-stat:
    fontFamily: Plus Jakarta Sans
    fontSize: 1.875rem
    fontWeight: '700'
    lineHeight: 2.25rem
    letterSpacing: -0.02em
  code-badge:
    fontFamily: JetBrains Mono
    fontSize: 0.6875rem
    fontWeight: '500'
    lineHeight: 0.875rem
    letterSpacing: 0.02em
  label-caps:
    fontFamily: Inter
    fontSize: 0.6875rem
    fontWeight: '600'
    lineHeight: 1rem
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-sm: 1rem
  margin: 2rem
  margin-sm: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system delivers an analytical, calm, and rigorous research discovery environment designed for qualitative and quantitative product researchers. Built on the structured simplicity of data science tooling (reminiscent of bespoke Streamlit research engines), it trades flashiness for unhurried clarity, high scanability, and evidence traceability.

### Visual Style
- **Streamlit-Grade Functionalism:** Architectural simplicity driven by structured sidebars, distinct collapsible blocks (`st.expander` paradigms), clean divider rules, and dense, highly organized content regions.
- **Warm Editorial Precision:** Offsets cold enterprise SaaS aesthetics with warm stone and limestone surfaces, grounding data inquiry with tactile readability.
- **Evidence-First Hierarchy:** Explicitly separates user quotes, verbatims, raw feedback extracts, and automated validation badges through strict color codes and structural callout cards.
- **Restrained Chrome:** Interactive chrome remains whisper-quiet in slate and teal, allowing qualitative quotes and statistical signal badges to dominate visual attention.

## Colors

The palette balances warm, paper-like background foundations with deep navy slate ink for typography and targeted teal for actionable anchors. Extended semantic accents deliver clear categorization for research validation pipelines.

### Foundation & Surfaces
- **Canvas Base (`#FBFBFA`):** The primary application canvas; minimizes eye fatigue during extended research review.
- **Surface Layer 1 (`#F4F3EF`):** Secondary container surface; used for the sidebar canvas, table headers, and inactive tab tracks.
- **Surface Layer 2 (`#EAE8E1`):** Subdued surface for nested quote containers, metadata ribbons, and hovering interactive states.
- **Structural Outlines (`#E2E8F0`):** 1px structural borders dividing panels, tables, and metric containers.

### Ink & Typography
- **Primary Ink (`#0F172A`):** Deep navy slate for primary titles, metric readouts, and active tab labels.
- **Secondary Ink (`#334155`):** Muted body text, verbatim customer feedback, and table row content.
- **Subtle Ink (`#64748B`):** Captions, timestamps, metadata labels, and helper microcopy.

### Semantic Validation System
- **Primary Research Accent (`#0D9488`):** Restrained teal for filters, primary action toggles, focused state rings, and active radio items. Darker anchor `#042F2E` provides depth for hover/pressed states, with `#14B8A6` for active pill highlights.
- **Validated / Approved (`#059669` base, `#ECFDF5` fill):** Confirmed researcher insights and validated behavioral patterns.
- **Auto-Validated Machine Extraction (`#6366F1` base, `#EEF2FF` fill):** AI/clustering extractions pending human researcher confirmation.
- **Attention / Needs Review (`#D97706` base, `#FFFBEB` fill):** Conflicting sentiment, unverified clusters, or sample size warnings.
- **Critical / Drop-off (`#DC2626` base, `#FEF2F2` fill):** Feedback indicating complete retrieval failure or photo loss concerns.

## Typography

The typographic hierarchy distinguishes narrative research quotes from data metrics and raw customer verbatim statements.

### Hierarchy & Voice
- **Headlines (`Plus Jakarta Sans`):** Clean, geometric humanist warmth that keeps the tool friendly yet analytical.
- **Narrative & UI Body (`Inter`):** Neutral, utilitarian body copy optimized for extended reading of feedback clusters, search queries, and pain point descriptions.
- **Monospace Tokens & Metadata (`JetBrains Mono`):** Applied to sample sizes, trace IDs, verbatim timestamps, query logs, and synthetic data disclaimers.
- **Case Rhythms:** Overline labels and metric indicators use `label-caps` in full uppercase with light tracking (`0.05em`) to clearly mark parameter groups without visual weight.

## Layout & Spacing

The layout adopts the signature desktop-first data workbench structure common to Streamlit and computational notebooks.

### Master Architecture
- **Sidebar (Fixed Left Column):** Fixed 280px to 320px width on desktop viewports. Hosts navigation pills, data filtering controls, cluster thresholds, and model parameters. Floats on `#F4F3EF` with a right border of `1px solid #E2E8F0`.
- **Main Canvas:** Fluid single-column or multi-column card grid with a maximum content constraint of `1440px` to maintain optimal line lengths for reading user quotes.
- **Grid Structure:** 12-column adaptive layout inside the main canvas. Metric cards typically span 3 or 4 columns; deep quote analysis tables span the full 12 columns.
- **Vertical Rhythm:** Strict multiples of `0.25rem` (4px baseline). Vertical element grouping relies on consistent `space-sm` for label-to-control links, `space-md` between form items, and `space-xl` between thematic analysis modules.

## Elevation & Depth

This design system rejects deep blur drop shadows in favor of a clean, planar, border-delimited architectural depth model.

### Depth Rules
- **Base Planar Depth:** Surfaces are differentiated by tonal shifts (`#FBFBFA` canvas against `#FFFFFF` elevated cards and `#F4F3EF` sidebars).
- **Outlines Over Shadows:** Every interactive or grouped surface utilizes a crisp `1px solid #E2E8F0` border.
- **Micro-Shadow on Interactive Focus:** Elevated cards in active hover or drop-down menus receive a subtle tinted ambient shadow: `0 2px 4px -1px rgba(15, 23, 42, 0.05), 0 1px 2px -1px rgba(15, 23, 42, 0.03)`.
- **Active Overlay / Expander Pop:** Floating tooltips and filter dropdowns leverage `0 8px 16px -4px rgba(15, 23, 42, 0.08)` bordered with `#E2E8F0` on pure `#FFFFFF`.

## Shapes

The interface embraces a tailored "soft" radius philosophy (`roundedness: 1` — 0.25rem / 4px base) to convey precision, tool-like utility, and crisp data boundaries.

### Shape Scale Rules
- **Base Form Elements & Metric Containers (`0.25rem`):** Buttons, inputs, metric tiles, and raw quote callout banners.
- **Group Containers & Expanders (`0.5rem` / `rounded-lg`):** Collapsible panels (`st.expander`), data frames, and navigation cluster containers.
- **Status & Attribute Badges (Pill `9999px`):** Status flags (`Auto-Validated`, `Needs Review`, `Sample Data`) use full pill radii to visually separate metadata tokens from rectangular interactive cards and inputs.

## Components

### Buttons & Action Controls
- **Primary Action:** Solid `#0D9488` fill, `#FFFFFF` text, `0.25rem` radius. On hover: `#0F766E`. Active: `#042F2E`. No drop shadow.
- **Secondary Action:** `#FFFFFF` background, `1px solid #E2E8F0`, `#1E293B` text. On hover: `#F4F3EF` background, `#0F172A` text.
- **Ghost Action:** Transparent background, `#334155` text. On hover: `#EAE8E1` background.

### Navigation Pills & Sidebar Radio
- **Sidebar Selection:** Stacked vertical list on `#F4F3EF`. Inactive items feature `#334155` text and transparent background.
- **Selected State:** Clean solid `#FFFFFF` card container with `1px solid #E2E8F0`, left indicator accent border (`3px solid #0D9488`), and `#0F172A` bold text.

### Metric Cards (`st.metric`)
- **Container:** `#FFFFFF` surface with `1px solid #E2E8F0` border and `space-md` internal padding.
- **Content Flow:** 
  1. Top: `label-caps` in `#64748B` detailing the metric title.
  2. Middle: `metric-stat` in `#0F172A` showing quantitative volume.
  3. Bottom: Delta pill or baseline contextual label indicating cluster percentage vs. prior release.

### Collapsible Accordions (`st.expander`)
- **Resting State:** `#FFFFFF` header surface with `1px solid #E2E8F0`. Chevron indicator anchored on the left.
- **Expanded State:** Content well drops down on `#FBFBFA` background with an internal top divider rule (`1px solid #E2E8F0`).

### Evidence Tracing Callouts & User Verbatims
- **Quote Callout:** Enclosed card with a thick `3px solid #0D9488` or `3px solid #6366F1` left border. Background `#F4F3EF`.
- **Source Tracking:** Monospaced attribution line at base (`JetBrains Mono`, `0.6875rem`) displaying query intention, retrieval status, and simulated user session ID.

### Pill Badges & Tags
- **Validation Tags:** Height `20px`, horizontal padding `8px`, radius `9999px`.
  - *Auto-Validated:* Background `#EEF2FF`, text `#4338CA`, border `1px solid #C7D2FE`.
  - *Approved:* Background `#ECFDF5`, text `#065F46`, border `1px solid #A7F3D0`.
  - *Warning:* Background `#FFFBEB`, text `#92400E`, border `1px solid #FDE68A`.
  - *Sample Data:* Background `#F1F5F9`, text `#475569`, border `1px solid #CBD5E1`.

### Data Tables
- **Header:** Sticky `#F4F3EF` row with uppercase muted labels (`label-caps`), bordered bottom `2px solid #CBD5E1`.
- **Rows:** Alternating rows (`#FFFFFF` and `#FBFBFA`), padded at `space-sm` vertically. Hover row background highlights to `#F1F5F9`.