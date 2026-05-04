# Burn Assessment Web — UI Redesign & Info Expansion

**Date:** 2026-05-04
**Project:** burn_assessment_web (Hugging Face Spaces, Gradio SDK)
**Goal:** Upgrade UI to a clinician-grade clinical decision aid that also presents well as a portfolio demo. Expand the displayed information from 8 simple text outputs to a structured 5-tab dashboard with a sticky KPI banner, while keeping the deployment platform (HF Spaces, Gradio) unchanged.

---

## 1. Audience & Goals

- **Primary user A — clinician** in ER / burn unit. Needs dense, clinical-grade information delivered in language and format they recognize. Output must be defensibly accurate and actionable.
- **Primary user C — demo viewer** (portfolio reviewer, recruiter, judge). Needs the app to feel polished, credible, and impressive at first glance.
- **Visual direction:** Clinical / EMR style — light background, blue accent, sterile typography (Inter), tabular density. No dark mode.

These two audiences are reconciled by making the clinical content itself the source of impressiveness — depth and quality of information, rendered cleanly.

---

## 2. Layout

A two-column page within Gradio Blocks plus custom CSS:

```
┌───────────────────────────────────────────────────────────┐
│  HEADER (gradient blue, 1 line title, subtitle)           │
├───────────────────┬───────────────────────────────────────┤
│  INPUT SIDEBAR    │  KPI BANNER (sticky, 5 tiles)         │
│  (340px)          ├───────────────────────────────────────┤
│  · Photo upload   │  TABS (5):                            │
│  · Patient data   │    📊 Ringkasan (default)             │
│  · Mechanism &    │    💧 Cairan                          │
│    Risks          │    📋 Orders                          │
│  · Submit btn     │    ⏱ Monitoring                       │
│  · Hint card      │    📚 Edukasi & Refs                  │
└───────────────────┴───────────────────────────────────────┘
```

The sidebar is fixed-width; the right side flexes. Banner sits above the tabs and remains visible as the user navigates between tabs.

---

## 3. Input Form (8 fields, 3 groups)

| Field | Type | Default | Required |
|---|---|---|---|
| Photo | image upload | — | ✓ |
| Usia (years) | number 0–120 | 25 | ✓ |
| Berat (kg) | number 1–300 | 60 | ✓ |
| Tinggi (cm) | number 30–250 | empty | optional |
| Jam sejak luka | number 0–72 | 1 | ✓ |
| Mekanisme | dropdown {Thermal, Electrical, Chemical} | Thermal | ✓ |
| Suspek inhalation injury | checkbox | false | — |
| Circumferential burn | checkbox | false | — |
| Komorbid | checkbox group {DM, CKD, Jantung, Hamil} | [] | — |

Visual treatment:
- Photo and Patient data shown plain.
- Mekanisme dropdown shown plain.
- Inhalation and Circumferential checkboxes given orange-bordered "warning" cards with a small explanatory line under each (face/neck soot for inhalation; melilit ekstremitas for circumferential).
- Komorbid rendered as pill chips.
- Submit button: full-width primary blue with shadow.
- Hint card under the button: bullet steps + note that *Jam sejak luka* drives Parkland catch-up rate.

---

## 4. KPI Banner

Always-visible above tabs. Five tiles in a single row:

| Tile | Primary value | Subtitle |
|---|---|---|
| PASIEN | `25y · 60kg · BSA 1.65m²` | `Adult · Thermal` |
| TBSA | `22.5%` (large) | `2nd-deg deep` |
| SEVERITY | `🔴 Major` (color-coded) | `>20% TBSA` |
| FLUID 24h | `5,400 mL` | `RL · Parkland` |
| DISPOSITION | `→ Burn ICU` (red if escalated) | `ABA criteria met` |

BSA shows `—` when height is empty. Severity icon and disposition color follow the underlying classification.

---

## 5. Tab Contents

### 5.1 📊 Ringkasan (default tab)
- **AI Detection** — burn degree, areas, characteristics from Gemini.
- **TBSA Breakdown by Region** — table of body parts × percentage with horizontal progress bars (Lund-Browder, age-adjusted).
- **AI Confidence** — gradient bar (yellow → green) with HIGH/MED/LOW label and a one-line caveat about confirming with a physical Lund-Browder chart.
- **Red Flags** — pill chips. Active flags red (e.g., "⚠ Inhalation injury", "⚠ TBSA >20%"). Cleared flags shown as gray "○ … — clear" pills so the screening is visibly comprehensive.

### 5.2 💧 Cairan
- **Parkland card** — total 24h volume, fluid type, formula breakdown.
- **Schedule** — two stacked cards: `0–8h` (first Parkland bucket, half of total) and `8–24h` (second bucket, the remaining 16 hours), each with rate (mL/jam) and volume.
- **Catch-up alert** — orange callout when `0 < hours_since < 8`, computing the catch-up rate as `first_8h_volume / (8 - hours_since)` so the patient still receives the prescribed first-8h volume by hour 8 from injury. Skipped if `hours_since ≥ 8` (callout becomes "8-jam pertama sudah terlewat — titrasi sesuai UO").
- **Formula Comparison table** — Parkland (default), Modified Brooke (2 mL/kg/%), Galveston (peds, only relevant when age <14; otherwise shown N/A in muted text).

### 5.3 📋 Orders
- **Disposition card** — color-coded (red for ICU/Burn Center, blue for ward, gray for OPD). Lists matched ABA criteria.
- **Initial Orders Checklist** — conditional bullet list including IV access, labs (CBC/BMP/ABG/lactate/CK/UA), imaging, tetanus, analgesia (morphine 0.05–0.1 mg/kg), Foley, NGT (TBSA >20%), NPO. Adds "Intubasi-ready" when inhalation flagged. Adds EKG + CK serial + rhabdo monitoring when mechanism is Electrical. Adds decontamination guidance when mechanism is Chemical.
- **Pain & Wound Care** — analgesia titration line and wound dressing recommendation by burn degree.

### 5.4 ⏱ Monitoring
- **24h Timeline** — vertical timeline with three monitoring milestones at 0–8h, 8–16h, 16–24h (split at 16h is for monitoring cadence, not Parkland buckets — the 8–24h bucket is shown as two halves here). First milestone is highlighted as the active/current window. Each milestone lists what to monitor (rate, urine output target 0.5–1 mL/kg/h, vitals, ABG recheck, manual TBSA recheck before grafting plan).
- **Clinical warning** — orange box with the existing `get_warning_message(tbsa, age)` output.

### 5.5 📚 Edukasi & Refs
- **Panduan Manajemen (RAG)** — explanation block from the existing RAG engine.
- **Referensi** — bullet list returned by RAG; falls back to a static set (ABA 2022, Parkland Baxter 1974, Lund-Browder, ATLS Burn Module) if RAG returns empty.

---

## 6. Code Structure

| File | Status | Responsibility |
|---|---|---|
| `app.py` | refactor | Gradio UI (Blocks, Tabs, sidebar). Wires inputs → `analyze()` → 6 HTML outputs (banner + 5 tabs). Custom CSS lives here. |
| `calculator.py` | extend | Add `modified_brooke(weight, tbsa)`, `mosteller_bsa(weight, height)`, `parkland_with_lag(weight, tbsa, hours_since)` returning catch-up rate fields. |
| `triage.py` | new | `classify(tbsa, age, mechanism, inhalation, circumferential, comorbid) → (disposition, reasons[])` based on ABA Burn Center Referral Criteria (TBSA ≥10% partial-thickness, any 3rd-degree, face/hands/feet/genitalia/major joints, electrical, chemical, inhalation, comorbid → Burn Center; TBSA ≥20% or any of the above → ICU). `red_flags(...) → list[(label, active)]` aggregating the four user-input flags + computed flags (e.g., TBSA >20%). |
| `orders.py` | new | `build_checklist(tbsa, age, weight, mechanism, inhalation, circumferential) → list[str]` returning conditional orders. |
| `renderers.py` | new | Pure functions: `banner_html(results)`, `summary_html(results)`, `fluid_html(results)`, `orders_html(results)`, `monitoring_html(results)`, `education_html(results)`. Each takes a results dict and returns an HTML string. No Gradio imports here. |
| `rag_engine.py` | unchanged | Existing ChromaDB + Gemini explanation. |
| `tests/test_triage.py` | new | Cover ABA criteria branches: TBSA thresholds, age extremes, mechanism, inhalation, circumferential, comorbid. |
| `tests/test_orders.py` | new | Cover conditional inclusions: inhalation toggle, mechanism switch, TBSA threshold for NGT. |
| `tests/test_calculator.py` | extend | Cover new functions: `modified_brooke`, `mosteller_bsa`, `parkland_with_lag` (no-lag, mid-lag, lag>=8h). |

---

## 7. Data Flow

```
analyze(image, age, weight, height, hours_since, mechanism,
        inhalation, circumferential, comorbid)
  │
  ├─► call_gemini_vision()           → ai dict
  ├─► calculator.parkland_with_lag() → fluid dict (8h, 16h, catchup_rate)
  ├─► calculator.modified_brooke()   → brooke dict (for comparison)
  ├─► calculator.mosteller_bsa()     → bsa_m2 (None if height empty)
  ├─► triage.classify()              → disposition + reasons
  ├─► triage.red_flags()             → list[(label, active)]
  ├─► orders.build_checklist()       → list[str]
  └─► rag_engine.query()             → explanation, refs

  ↓ collected into results dict ↓

renderers.{banner,summary,fluid,orders,monitoring,education}_html(results)
  ↓
return (banner_html, summary_html, fluid_html, orders_html,
        monitoring_html, education_html)
```

The 6-tuple maps to six `gr.HTML` components: one above the tabs (banner), one inside each tab.

---

## 8. Error Handling & Edge Cases

| Scenario | Behavior |
|---|---|
| No image | Show validation message in banner area + Ringkasan tab; other tabs render an empty placeholder. |
| Weight 0 or empty | Inline error in sidebar; analysis short-circuits. |
| Gemini fails on all models | Banner shows ⚠ icon; Ringkasan tab shows the existing failure message + retry guidance; other tabs render "Analysis incomplete" placeholders. |
| Height empty | Banner shows `BSA —`; analysis proceeds. |
| `hours_since ≥ 8` | Catch-up alert replaced by "8-jam pertama sudah terlewat — titrasi UO". |
| RAG fails | Education tab falls back to static text + canonical refs. |
| Age < 14 | Galveston row in formula comparison promoted; Modified Brooke deprioritized. |
| Mechanism = Electrical | Orders adds EKG, CK serial, rhabdo monitoring; banner mechanism subtitle reflects it. |
| Mechanism = Chemical | Orders adds decontamination + irrigation guidance; remove tetanus offer is unchanged. |

---

## 9. Testing

- Existing pytest suite continues to pass.
- New unit tests for `triage.py`, `orders.py`, and the new `calculator` functions. All tests are pure-function (no API calls).
- Renderers are pure str-returning functions and can be smoke-tested by calling each with a representative results dict.
- Manual verification: golden-path flow (typical adult major burn + inhalation), edge flows (peds, electrical, hours_since>8, height empty, RAG failure simulated by unsetting key).

---

## 10. Out of Scope

The following are deliberately not part of this redesign:

- Switching SDK away from Gradio (would break HF Space deployment).
- Authentication, multi-patient state, persistence across sessions.
- Image annotation overlays (drawing on the burn photo).
- PDF export of the assessment.
- i18n beyond the existing Indonesian + English clinical-term mix.

These can become follow-up specs if needed.
