# Burn Assessment UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing Gradio-on-HF-Spaces burn assessment app from 8 plain text outputs to a clinician-grade dashboard: 8-field input form, sticky 5-tile KPI banner, and 5-tab output (Ringkasan / Cairan / Orders / Monitoring / Edukasi & Refs).

**Architecture:** Layered. Pure-logic modules (`calculator.py` extended, new `triage.py`, new `orders.py`) are deterministic and fully tested. A new `renderers.py` produces tab HTML strings from a results dict — no logic, just templating. `app.py` is reduced to wiring: collect inputs → call `analyze()` → return a 6-tuple of HTML strings to six `gr.HTML` outputs (1 banner + 5 tabs).

**Tech Stack:** Python 3.10+, Gradio 4.44+, google-genai, ChromaDB, pytest. Stays on HF Spaces (Gradio SDK).

**Spec:** `docs/superpowers/specs/2026-05-04-burn-ui-redesign-design.md`

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `calculator.py` | extend | Add `mosteller_bsa`, `modified_brooke`, `parkland_with_lag`. Keep existing functions. |
| `triage.py` | create | `classify(...)` + `red_flags(...)` — ABA referral criteria, deterministic. |
| `orders.py` | create | `build_checklist(...)` — conditional initial-orders generator. |
| `renderers.py` | create | Six pure functions: `banner_html`, `summary_html`, `fluid_html`, `orders_html`, `monitoring_html`, `education_html`. Each takes a results dict, returns HTML string. |
| `app.py` | refactor | New input form (8 fields), new `analyze()` returning a 6-tuple of HTML, new `build_ui()` with banner + tabs, expanded CSS. |
| `tests/test_calculator.py` | extend | Cover the new calculator functions. |
| `tests/test_triage.py` | create | Cover ABA branches. |
| `tests/test_orders.py` | create | Cover conditional inclusions. |
| `tests/test_renderers.py` | create | Smoke tests: each renderer returns non-empty HTML containing the key fields from the input dict. |

---

## Task 1: Extend `calculator.py` with BSA, Modified Brooke, Parkland-with-lag

**Files:**
- Modify: `calculator.py` (append new functions)
- Modify: `tests/test_calculator.py` (append new tests)

- [ ] **Step 1: Write failing tests for the three new functions**

Append to `tests/test_calculator.py`:

```python
# ── Mosteller BSA ────────────────────────────────────────────────────────────

def test_mosteller_bsa_typical_adult():
    from calculator import mosteller_bsa
    # Mosteller: sqrt((height_cm * weight_kg) / 3600)
    # 170cm, 70kg → sqrt(170*70/3600) = sqrt(3.305...) ≈ 1.818
    bsa = mosteller_bsa(weight_kg=70, height_cm=170)
    assert abs(bsa - 1.818) < 0.01


def test_mosteller_bsa_returns_none_when_height_missing():
    from calculator import mosteller_bsa
    assert mosteller_bsa(weight_kg=70, height_cm=None) is None
    assert mosteller_bsa(weight_kg=70, height_cm=0) is None


def test_mosteller_bsa_returns_none_when_weight_missing():
    from calculator import mosteller_bsa
    assert mosteller_bsa(weight_kg=0, height_cm=170) is None


# ── Modified Brooke ──────────────────────────────────────────────────────────

def test_modified_brooke_basic():
    from calculator import modified_brooke
    # 2 mL × 60 kg × 22.5% = 2700 mL
    result = modified_brooke(weight_kg=60, tbsa_percent=22.5)
    assert result["total_24h_ml"] == 2700.0
    assert result["first_8h_ml"] == 1350.0
    assert result["next_16h_ml"] == 1350.0
    assert result["fluid_type"] == "Ringer's Lactate"


def test_modified_brooke_zero_tbsa():
    from calculator import modified_brooke
    result = modified_brooke(weight_kg=70, tbsa_percent=0)
    assert result["total_24h_ml"] == 0.0


# ── Parkland with lag (catch-up) ─────────────────────────────────────────────

def test_parkland_with_lag_no_lag():
    from calculator import parkland_with_lag
    # hours_since=0: catch-up rate equals normal rate
    result = parkland_with_lag(weight_kg=60, tbsa_percent=22.5, hours_since=0)
    assert result["total_24h_ml"] == 5400.0
    assert result["first_8h_ml"] == 2700.0
    assert result["catchup_rate_mlph"] == 337.5  # 2700 / 8
    assert result["lag_status"] == "on_time"


def test_parkland_with_lag_mid_lag():
    from calculator import parkland_with_lag
    # 1 hour late, 7 hours remaining: 2700 / 7 ≈ 385.71
    result = parkland_with_lag(weight_kg=60, tbsa_percent=22.5, hours_since=1)
    assert abs(result["catchup_rate_mlph"] - 385.71) < 0.1
    assert result["lag_status"] == "catching_up"
    assert result["hours_remaining_first_8h"] == 7


def test_parkland_with_lag_eight_or_more_hours_late():
    from calculator import parkland_with_lag
    result = parkland_with_lag(weight_kg=60, tbsa_percent=22.5, hours_since=8)
    assert result["lag_status"] == "first_8h_passed"
    assert result["catchup_rate_mlph"] is None
    assert result["hours_remaining_first_8h"] == 0


def test_parkland_with_lag_well_past_first_8h():
    from calculator import parkland_with_lag
    result = parkland_with_lag(weight_kg=60, tbsa_percent=22.5, hours_since=15)
    assert result["lag_status"] == "first_8h_passed"
    assert result["catchup_rate_mlph"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/irhammohammad/Documents/Code/Random/MedAssistant/burn_assessment_web
source venv/bin/activate
pytest tests/test_calculator.py -v
```

Expected: FAIL with `ImportError: cannot import name 'mosteller_bsa'` (and similar for the others).

- [ ] **Step 3: Implement the three new functions in `calculator.py`**

Append to `calculator.py`:

```python
import math


def mosteller_bsa(weight_kg: float, height_cm) -> float | None:
    """
    Mosteller BSA formula: sqrt((height_cm * weight_kg) / 3600).

    Returns None if height or weight is missing/invalid (cannot compute BSA
    without both). Caller should display "—" when None is returned.
    """
    if not height_cm or weight_kg <= 0:
        return None
    try:
        h = float(height_cm)
        w = float(weight_kg)
    except (TypeError, ValueError):
        return None
    if h <= 0 or w <= 0:
        return None
    return round(math.sqrt((h * w) / 3600.0), 3)


def modified_brooke(weight_kg: float, tbsa_percent: float) -> dict:
    """
    Modified Brooke formula: 2 mL × weight(kg) × TBSA(%).
    Same shape as calculate_parkland() return dict for consistency.
    """
    total = 2.0 * weight_kg * tbsa_percent
    first_half = total / 2.0
    second_half = total / 2.0
    return {
        "total_24h_ml":        round(total, 2),
        "first_8h_ml":         round(first_half, 2),
        "next_16h_ml":         round(second_half, 2),
        "fluid_type":          "Ringer's Lactate",
        "rate_first_8h_mlph":  round(first_half / 8.0, 2) if total else 0.0,
        "rate_next_16h_mlph":  round(second_half / 16.0, 2) if total else 0.0,
    }


def parkland_with_lag(weight_kg: float, tbsa_percent: float, hours_since: float) -> dict:
    """
    Parkland with catch-up rate when patient presents late.

    The Parkland formula schedules half the 24h volume in the first 8 hours
    *from time of injury* (not from arrival). When hours_since > 0, the rate
    must be increased so the prescribed first-8h volume is delivered by hour 8.

    Returns the standard Parkland dict plus:
        catchup_rate_mlph     – mL/hour for remaining first-8h window, or None
        hours_remaining_first_8h – hours left in the first-8h window
        lag_status            – "on_time" | "catching_up" | "first_8h_passed"
    """
    base = calculate_parkland(weight_kg, tbsa_percent)
    if hours_since <= 0:
        base["catchup_rate_mlph"] = base["rate_first_8h_mlph"]
        base["hours_remaining_first_8h"] = 8
        base["lag_status"] = "on_time"
    elif hours_since < 8:
        remaining = 8 - hours_since
        base["catchup_rate_mlph"] = round(base["first_8h_ml"] / remaining, 2)
        base["hours_remaining_first_8h"] = remaining
        base["lag_status"] = "catching_up"
    else:
        base["catchup_rate_mlph"] = None
        base["hours_remaining_first_8h"] = 0
        base["lag_status"] = "first_8h_passed"
    return base
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_calculator.py -v
```

Expected: all tests pass (existing + 8 new).

- [ ] **Step 5: Commit**

```bash
git add calculator.py tests/test_calculator.py
git commit -m "feat(calculator): add mosteller_bsa, modified_brooke, parkland_with_lag"
```

---

## Task 2: Create `triage.py` with ABA classification + red flag aggregation

**Files:**
- Create: `triage.py`
- Create: `tests/test_triage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_triage.py`:

```python
"""Tests for triage.py — ABA Burn Center Referral Criteria + red flags."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from triage import classify, red_flags


# ── classify() ───────────────────────────────────────────────────────────────

def _kwargs(**overrides):
    base = dict(
        tbsa=5.0, age=30, mechanism="Thermal",
        inhalation=False, circumferential=False, comorbid=[],
        burn_degree="Second degree superficial",
    )
    base.update(overrides)
    return base


def test_classify_minor_burn_outpatient():
    disposition, reasons = classify(**_kwargs(tbsa=4.0))
    assert disposition == "Outpatient / Klinik Rawat Jalan"
    assert reasons == []


def test_classify_moderate_to_ward():
    disposition, reasons = classify(**_kwargs(tbsa=12.0))
    assert disposition == "Bangsal Bedah / Burn Unit"
    assert any("TBSA" in r for r in reasons)


def test_classify_burn_center_for_partial_thickness_ge_10():
    disposition, reasons = classify(**_kwargs(tbsa=10.0))
    assert "Burn Center" in disposition
    assert any("TBSA ≥ 10%" in r for r in reasons)


def test_classify_icu_for_tbsa_over_20():
    disposition, reasons = classify(**_kwargs(tbsa=22.0))
    assert "ICU" in disposition
    assert any("TBSA > 20%" in r for r in reasons)


def test_classify_icu_for_inhalation():
    disposition, reasons = classify(**_kwargs(tbsa=8.0, inhalation=True))
    assert "ICU" in disposition
    assert any("Inhalation" in r for r in reasons)


def test_classify_burn_center_for_electrical():
    disposition, reasons = classify(**_kwargs(tbsa=5.0, mechanism="Electrical"))
    assert "Burn Center" in disposition
    assert any("Electrical" in r for r in reasons)


def test_classify_burn_center_for_chemical():
    disposition, reasons = classify(**_kwargs(tbsa=5.0, mechanism="Chemical"))
    assert "Burn Center" in disposition
    assert any("Chemical" in r for r in reasons)


def test_classify_burn_center_for_circumferential():
    disposition, reasons = classify(**_kwargs(tbsa=8.0, circumferential=True))
    assert "Burn Center" in disposition
    assert any("Circumferential" in r for r in reasons)


def test_classify_burn_center_for_third_degree():
    disposition, reasons = classify(**_kwargs(tbsa=3.0, burn_degree="Third degree"))
    assert "Burn Center" in disposition
    assert any("3rd-degree" in r for r in reasons)


def test_classify_burn_center_for_pediatric_with_tbsa_5():
    disposition, reasons = classify(**_kwargs(tbsa=5.0, age=4))
    assert "Burn Center" in disposition
    assert any("Pediatric" in r for r in reasons)


def test_classify_burn_center_for_geriatric_with_comorbid():
    disposition, reasons = classify(**_kwargs(tbsa=8.0, age=65, comorbid=["DM"]))
    assert "Burn Center" in disposition
    assert any("Comorbid" in r for r in reasons)


def test_icu_dominates_over_burn_center():
    # TBSA > 20% AND inhalation: should land at ICU, not Burn Center alone.
    disposition, _ = classify(**_kwargs(tbsa=25.0, inhalation=True))
    assert disposition.startswith("Burn ICU")


# ── red_flags() ──────────────────────────────────────────────────────────────

def test_red_flags_returns_all_four_inputs_plus_tbsa():
    flags = red_flags(tbsa=8.0, inhalation=False, circumferential=False, comorbid=[])
    labels = [label for label, _active in flags]
    assert "Inhalation injury" in labels
    assert "Circumferential burn" in labels
    assert "Komorbid" in labels
    assert "TBSA > 20%" in labels


def test_red_flags_active_state_reflects_inputs():
    flags = red_flags(tbsa=25.0, inhalation=True, circumferential=False, comorbid=["DM"])
    flag_map = dict(flags)
    assert flag_map["Inhalation injury"] is True
    assert flag_map["Circumferential burn"] is False
    assert flag_map["Komorbid"] is True
    assert flag_map["TBSA > 20%"] is True


def test_red_flags_tbsa_threshold_not_active_below_20():
    flags = red_flags(tbsa=18.0, inhalation=False, circumferential=False, comorbid=[])
    flag_map = dict(flags)
    assert flag_map["TBSA > 20%"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_triage.py -v
```

Expected: FAIL — `triage` module does not exist.

- [ ] **Step 3: Implement `triage.py`**

Create `triage.py`:

```python
"""
triage.py
=========
ABA Burn Center Referral Criteria → disposition (deterministic, rule-based).
Red-flag aggregator for the Ringkasan tab.

References:
- American Burn Association Burn Center Referral Criteria (2022)
"""

from typing import Iterable


def classify(
    *,
    tbsa: float,
    age: int,
    mechanism: str,
    inhalation: bool,
    circumferential: bool,
    comorbid: Iterable[str],
    burn_degree: str,
) -> tuple[str, list[str]]:
    """
    Return (disposition, reasons[]).

    Disposition tiers (most-acute first):
        "Burn ICU / Burn Center"        – TBSA > 20%, OR inhalation,
                                          OR any of the above on top of any
                                          burn-center criteria.
        "Burn Center (Refer)"           – any ABA referral criterion met.
        "Bangsal Bedah / Burn Unit"     – TBSA 5–10% partial thickness.
        "Outpatient / Klinik Rawat Jalan" – TBSA <5%, no other criteria.

    `reasons` is a human-readable list of which criteria fired.
    """
    reasons: list[str] = []

    is_third_degree = "Third degree" in (burn_degree or "")
    is_pediatric = age < 5
    is_geriatric = age >= 65
    has_comorbid = bool(list(comorbid))

    # ABA Burn Center Referral Criteria
    if tbsa >= 10.0:
        reasons.append(f"TBSA ≥ 10% partial-thickness ({tbsa:.1f}%)")
    if is_third_degree:
        reasons.append("Any 3rd-degree burn")
    if mechanism == "Electrical":
        reasons.append("Electrical burn (rhabdomyolysis/cardiac risk)")
    if mechanism == "Chemical":
        reasons.append("Chemical burn (decontamination required)")
    if inhalation:
        reasons.append("Inhalation injury suspected")
    if circumferential:
        reasons.append("Circumferential burn (escharotomy risk)")
    if is_pediatric and tbsa >= 5.0:
        reasons.append(f"Pediatric (age {age}) with TBSA ≥ 5%")
    if is_geriatric and has_comorbid:
        reasons.append(f"Comorbid + age ≥65 ({', '.join(comorbid)})")

    # Escalation to ICU
    icu_reasons: list[str] = []
    if tbsa > 20.0:
        icu_reasons.append(f"TBSA > 20% ({tbsa:.1f}%)")
    if inhalation:
        icu_reasons.append("Inhalation injury suspected")

    if icu_reasons:
        # ICU disposition includes ICU-level reasons first, then any other
        # burn-center criteria.
        all_reasons = icu_reasons + [r for r in reasons if r not in icu_reasons]
        return "Burn ICU / Burn Center", all_reasons

    if reasons:
        return "Burn Center (Refer)", reasons

    if tbsa >= 5.0:
        return "Bangsal Bedah / Burn Unit", [f"TBSA {tbsa:.1f}% (5–10% range)"]

    return "Outpatient / Klinik Rawat Jalan", []


def red_flags(
    *,
    tbsa: float,
    inhalation: bool,
    circumferential: bool,
    comorbid: Iterable[str],
) -> list[tuple[str, bool]]:
    """
    Return a fixed list of (label, active) tuples for the Ringkasan red-flag chips.

    Order is stable so the UI can render "active" red and "clear" gray reliably.
    """
    return [
        ("Inhalation injury", bool(inhalation)),
        ("Circumferential burn", bool(circumferential)),
        ("Komorbid", bool(list(comorbid))),
        ("TBSA > 20%", tbsa > 20.0),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_triage.py -v
```

Expected: all 16 tests pass.

- [ ] **Step 5: Commit**

```bash
git add triage.py tests/test_triage.py
git commit -m "feat: add triage.py with ABA classification and red flags"
```

---

## Task 3: Create `orders.py` with conditional initial-orders generator

**Files:**
- Create: `orders.py`
- Create: `tests/test_orders.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orders.py`:

```python
"""Tests for orders.py — conditional initial-orders checklist."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orders import build_checklist


def _kwargs(**overrides):
    base = dict(
        tbsa=15.0, weight_kg=60,
        mechanism="Thermal", inhalation=False, circumferential=False,
    )
    base.update(overrides)
    return base


def test_baseline_orders_always_present():
    items = build_checklist(**_kwargs())
    text = " | ".join(items)
    assert "IV access" in text
    assert "Lab" in text
    assert "Tetanus" in text
    assert "Analgesia" in text
    assert "Foley" in text


def test_ngt_added_when_tbsa_over_20():
    items_low = build_checklist(**_kwargs(tbsa=15.0))
    items_high = build_checklist(**_kwargs(tbsa=22.0))
    assert not any("NGT" in i for i in items_low)
    assert any("NGT" in i for i in items_high)


def test_inhalation_adds_intubation_ready_and_cxr():
    items = build_checklist(**_kwargs(inhalation=True))
    text = " | ".join(items)
    assert "Intubasi" in text or "intubation" in text.lower()
    assert "CXR" in text


def test_electrical_adds_ekg_and_ck_serial():
    items = build_checklist(**_kwargs(mechanism="Electrical"))
    text = " | ".join(items)
    assert "EKG" in text
    assert "CK serial" in text or "rhabdo" in text.lower()


def test_chemical_adds_decontamination():
    items = build_checklist(**_kwargs(mechanism="Chemical"))
    text = " | ".join(items)
    assert "Dekontaminasi" in text or "decontamin" in text.lower()
    assert "irigasi" in text.lower() or "irrigat" in text.lower()


def test_circumferential_adds_escharotomy_consult():
    items = build_checklist(**_kwargs(circumferential=True))
    text = " | ".join(items)
    assert "Escharotomy" in text or "escharotomy" in text.lower()


def test_analgesia_dose_uses_weight():
    # 60 kg → morphine 3-6 mg (0.05-0.1 mg/kg)
    items = build_checklist(**_kwargs(weight_kg=60))
    text = " | ".join(items)
    assert "3" in text and "6" in text  # range present
    assert "mg" in text.lower()


def test_central_line_added_for_large_tbsa():
    items_low = build_checklist(**_kwargs(tbsa=15.0))
    items_high = build_checklist(**_kwargs(tbsa=35.0))
    assert not any("central" in i.lower() for i in items_low)
    assert any("central" in i.lower() for i in items_high)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_orders.py -v
```

Expected: FAIL — `orders` module does not exist.

- [ ] **Step 3: Implement `orders.py`**

Create `orders.py`:

```python
"""
orders.py
=========
Conditional initial-orders checklist generator for burn assessment.
Pure function: inputs in, list of order strings out. No I/O.
"""


def build_checklist(
    *,
    tbsa: float,
    weight_kg: float,
    mechanism: str,
    inhalation: bool,
    circumferential: bool,
) -> list[str]:
    """
    Return a list of clinician-facing order strings, ordered by priority.
    Each string is suitable for direct rendering in a checklist.
    """
    items: list[str] = []

    # Vascular access
    if tbsa >= 30.0:
        items.append(
            "IV access — 2× large-bore (16-18G) perifer + central line "
            "(TBSA ≥ 30%)"
        )
    else:
        items.append("IV access — 2× large-bore (16-18G) perifer")

    # Labs
    lab_extras: list[str] = []
    if mechanism == "Electrical":
        lab_extras.append("CK serial")
    lab_base = "CBC, BMP, ABG + carboxyHb, lactate, urinalisis"
    if lab_extras:
        items.append(f"Lab — {lab_base}, {', '.join(lab_extras)}")
    else:
        items.append(f"Lab — {lab_base}")

    # Imaging
    imaging_parts: list[str] = []
    if inhalation:
        imaging_parts.append("CXR (inhalation suspek)")
    if mechanism == "Electrical":
        imaging_parts.append("EKG 12-lead + monitoring kontinu")
    if imaging_parts:
        items.append("Imaging / EKG — " + " · ".join(imaging_parts))

    # Tetanus
    items.append("Tetanus — TT booster bila >5 thn / status tidak jelas")

    # Analgesia (morphine 0.05–0.1 mg/kg → range)
    low = round(0.05 * weight_kg, 1)
    high = round(0.10 * weight_kg, 1)
    items.append(
        f"Analgesia — Morfin IV {low:g}-{high:g} mg titrasi q5-10min "
        f"(0.05-0.1 mg/kg) · target NRS <4"
    )

    # Foley
    items.append("Foley catheter — monitor urine output 0.5-1 mL/kg/jam")

    # NGT for large burns (gastric ileus risk)
    if tbsa > 20.0:
        items.append("NGT — pasang (TBSA > 20%, risiko gastric ileus)")

    # NPO
    items.append("NPO — antisipasi anestesi/intubasi")

    # Inhalation-specific
    if inhalation:
        items.append(
            "⚠ Intubasi-ready — siapkan ETT, lakukan early intubation bila "
            "stridor / hoarseness / progressif"
        )

    # Chemical decontamination
    if mechanism == "Chemical":
        items.append(
            "Dekontaminasi — copot pakaian terkontaminasi, irigasi air mengalir "
            "≥ 20 menit (alkali ≥ 1 jam)"
        )

    # Circumferential
    if circumferential:
        items.append(
            "Escharotomy konsul — circumferential burn, monitor distal pulses "
            "& compartment pressure"
        )

    return items
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_orders.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add orders.py tests/test_orders.py
git commit -m "feat: add orders.py with conditional initial-orders checklist"
```

---

## Task 4: Create `renderers.py` — banner + summary

**Files:**
- Create: `renderers.py`
- Create: `tests/test_renderers.py`

- [ ] **Step 1: Write the failing smoke tests**

Create `tests/test_renderers.py`:

```python
"""Smoke tests for renderers.py — each renderer returns non-empty HTML
containing the key fields from the input dict."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from renderers import banner_html, summary_html


def _sample_results():
    return {
        "patient": {
            "age": 25, "weight": 60.0, "height": 170.0, "bsa_m2": 1.65,
            "mechanism": "Thermal",
        },
        "ai": {
            "burn_degree": "Second degree deep",
            "tbsa": 22.5,
            "areas": ["dada anterior", "lengan kiri"],
            "description": "luka berbatas tegas, eksudasi",
            "confidence": "high",
        },
        "severity": "Major / Severe",
        "fluid": {
            "total_24h_ml": 5400.0, "first_8h_ml": 2700.0, "next_16h_ml": 2700.0,
            "rate_first_8h_mlph": 337.5, "rate_next_16h_mlph": 168.75,
            "fluid_type": "Ringer's Lactate",
            "catchup_rate_mlph": 385.71, "hours_remaining_first_8h": 7,
            "lag_status": "catching_up",
        },
        "brooke": {"total_24h_ml": 2700.0},
        "disposition": "Burn ICU / Burn Center",
        "disposition_reasons": ["TBSA > 20% (22.5%)", "Inhalation injury suspected"],
        "red_flags": [
            ("Inhalation injury", True),
            ("Circumferential burn", False),
            ("Komorbid", False),
            ("TBSA > 20%", True),
        ],
        "orders": ["IV access — 2× large-bore", "Lab — CBC, BMP"],
        "rag_explanation": "Pasien dewasa dengan luka bakar...",
        "references": ["ABA Guidelines 2022", "Parkland Baxter 1974"],
        "warning": "⚠️ MAJOR BURN: TBSA > 20%",
        "hours_since": 1,
    }


# ── banner_html ──────────────────────────────────────────────────────────────

def test_banner_html_contains_all_five_kpis():
    html = banner_html(_sample_results())
    assert "25y" in html and "60" in html  # patient
    assert "22.5" in html  # tbsa
    assert "Major" in html  # severity
    assert "5,400" in html or "5400" in html  # fluid
    assert "Burn ICU" in html  # disposition


def test_banner_html_shows_dash_when_bsa_missing():
    r = _sample_results()
    r["patient"]["bsa_m2"] = None
    html = banner_html(r)
    assert "—" in html  # BSA placeholder


# ── summary_html ─────────────────────────────────────────────────────────────

def test_summary_html_includes_ai_detection_and_areas():
    html = summary_html(_sample_results())
    assert "Second degree deep" in html
    assert "dada anterior" in html
    assert "lengan kiri" in html


def test_summary_html_renders_red_flags_with_active_styling():
    html = summary_html(_sample_results())
    assert "Inhalation injury" in html
    assert "Circumferential burn" in html
    # Active flag should differ from clear flag in markup. Check both branches
    # appear.
    assert "active" in html.lower() or "fee2e2" in html.lower()
    assert "clear" in html.lower() or "f1f5f9" in html.lower()


def test_summary_html_renders_confidence_bar():
    html = summary_html(_sample_results())
    assert "HIGH" in html
    assert "confidence" in html.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderers.py -v
```

Expected: FAIL — `renderers` does not exist.

- [ ] **Step 3: Implement `renderers.py` (banner + summary first)**

Create `renderers.py`:

```python
"""
renderers.py
============
Pure HTML rendering functions. Each takes a results dict and returns an
HTML string. No Gradio imports, no I/O.

The results dict shape is the contract between analyze() and the renderers.
See tests/test_renderers.py::_sample_results for the canonical example.
"""

from html import escape


# ── helpers ──────────────────────────────────────────────────────────────────

def _fmt_int(n) -> str:
    if n is None:
        return "—"
    try:
        return f"{int(round(float(n))):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(n, decimals=1) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n):.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def _disposition_color(disposition: str) -> str:
    d = (disposition or "").lower()
    if "icu" in d:
        return "#DC2626"  # red
    if "refer" in d or "burn center" in d:
        return "#EA580C"  # orange
    if "bangsal" in d or "ward" in d:
        return "#2563EB"  # blue
    return "#16A34A"      # green (outpatient)


def _severity_icon(severity: str) -> str:
    s = (severity or "").lower()
    if "critical" in s:
        return "🚨"
    if "major" in s or "severe" in s:
        return "🔴"
    if "moderate" in s:
        return "🟡"
    return "🟢"


# ── banner ───────────────────────────────────────────────────────────────────

def banner_html(r: dict) -> str:
    p = r.get("patient", {})
    ai = r.get("ai", {})
    fluid = r.get("fluid", {})

    age = p.get("age", "—")
    weight = p.get("weight", "—")
    bsa = p.get("bsa_m2")
    bsa_str = f"BSA {bsa:.2f}m²" if isinstance(bsa, (int, float)) else "BSA —"
    mech = escape(str(p.get("mechanism", "—")))
    age_cat = "Pediatric" if isinstance(age, int) and age < 14 else (
        "Geriatric" if isinstance(age, int) and age >= 65 else "Adult"
    )

    tbsa = ai.get("tbsa", 0.0)
    degree = escape(str(ai.get("burn_degree", "—")))
    severity = r.get("severity", "—")
    sev_icon = _severity_icon(severity)
    disposition = r.get("disposition", "—")
    disp_color = _disposition_color(disposition)
    fluid_total = fluid.get("total_24h_ml")

    return f"""
    <div class="kpi-banner">
      <div class="kpi-label">PATIENT BANNER · KPI</div>
      <div class="kpi-grid">
        <div class="kpi-tile">
          <div class="kpi-key">PASIEN</div>
          <div class="kpi-val">{age}y · {weight}kg · {bsa_str}</div>
          <div class="kpi-sub">{age_cat} · {mech}</div>
        </div>
        <div class="kpi-tile">
          <div class="kpi-key">TBSA</div>
          <div class="kpi-val kpi-big" style="color:#1E40AF">{tbsa:.1f}<span style="font-size:.6em;color:#64748B">%</span></div>
          <div class="kpi-sub">{degree}</div>
        </div>
        <div class="kpi-tile">
          <div class="kpi-key">SEVERITY</div>
          <div class="kpi-val">{sev_icon} {escape(severity)}</div>
          <div class="kpi-sub">{_severity_subtitle(tbsa)}</div>
        </div>
        <div class="kpi-tile">
          <div class="kpi-key">FLUID 24h</div>
          <div class="kpi-val">{_fmt_int(fluid_total)} mL</div>
          <div class="kpi-sub">RL · Parkland</div>
        </div>
        <div class="kpi-tile">
          <div class="kpi-key">DISPOSITION</div>
          <div class="kpi-val" style="color:{disp_color}">→ {escape(disposition)}</div>
          <div class="kpi-sub">{("ABA criteria met" if disposition != "Outpatient / Klinik Rawat Jalan" else "—")}</div>
        </div>
      </div>
    </div>
    """


def _severity_subtitle(tbsa: float) -> str:
    if tbsa > 40: return "> 40% TBSA"
    if tbsa > 20: return "> 20% TBSA"
    if tbsa >= 10: return "10–20% TBSA"
    return "< 10% TBSA"


# ── summary tab ──────────────────────────────────────────────────────────────

def summary_html(r: dict) -> str:
    ai = r.get("ai", {})
    flags = r.get("red_flags", [])

    degree = escape(str(ai.get("burn_degree", "—")))
    areas = ", ".join(escape(a) for a in ai.get("areas", [])) or "—"
    desc = escape(str(ai.get("description", "—")))
    conf = str(ai.get("confidence", "medium")).lower()

    conf_pct = {"high": 85, "medium": 60, "low": 30}.get(conf, 50)
    conf_label = conf.upper()
    conf_color = {"high": "#0F766E", "medium": "#A16207", "low": "#B91C1C"}.get(
        conf, "#475569"
    )

    flag_chips = []
    for label, active in flags:
        if active:
            flag_chips.append(
                f'<span class="flag-chip flag-active" style="background:#FEE2E2;color:#991B1B">⚠ {escape(label)}</span>'
            )
        else:
            flag_chips.append(
                f'<span class="flag-chip flag-clear" style="background:#F1F5F9;color:#64748B">○ {escape(label)} — clear</span>'
            )
    flag_html = "".join(flag_chips) or '<span class="kpi-sub">—</span>'

    return f"""
    <div class="tab-section">
      <div class="sec-label">📷 AI DETECTION</div>
      <div class="grid-2">
        <div><span class="muted">Derajat:</span> <b>{degree}</b></div>
        <div><span class="muted">Areas:</span> {areas}</div>
        <div style="grid-column:1/-1"><span class="muted">Karakteristik:</span> {desc}</div>
      </div>
    </div>

    <div class="tab-section">
      <div class="sec-label">🤖 AI CONFIDENCE</div>
      <div class="conf-row">
        <div class="conf-bar"><div class="conf-fill" style="width:{conf_pct}%;background:linear-gradient(to right,#FBBF24,#34D399)"></div></div>
        <div style="font-weight:700;color:{conf_color}">{conf_label} ({conf_pct}%)</div>
      </div>
      <div class="muted small">Konfirmasi manual dengan Lund-Browder chart fisik tetap dianjurkan.</div>
    </div>

    <div class="tab-section">
      <div class="sec-label">🚩 RED FLAGS</div>
      <div class="flag-row">{flag_html}</div>
    </div>
    """
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderers.py -v
```

Expected: 4 banner/summary tests pass.

- [ ] **Step 5: Commit**

```bash
git add renderers.py tests/test_renderers.py
git commit -m "feat(renderers): add banner_html and summary_html"
```

---

## Task 5: Add `fluid_html` and `orders_html` to `renderers.py`

**Files:**
- Modify: `renderers.py` (append two functions)
- Modify: `tests/test_renderers.py` (append tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_renderers.py`:

```python
from renderers import fluid_html, orders_html


def test_fluid_html_contains_parkland_and_brooke_totals():
    html = fluid_html(_sample_results())
    assert "5,400" in html or "5400" in html  # Parkland
    assert "2,700" in html or "2700" in html  # Brooke


def test_fluid_html_renders_catchup_alert_when_lagging():
    html = fluid_html(_sample_results())
    assert "Tertinggal" in html or "catch" in html.lower()
    assert "385" in html  # catchup rate ~385.71


def test_fluid_html_renders_passed_message_when_first_8h_passed():
    r = _sample_results()
    r["fluid"]["lag_status"] = "first_8h_passed"
    r["fluid"]["catchup_rate_mlph"] = None
    html = fluid_html(r)
    assert "terlewat" in html.lower() or "passed" in html.lower()


def test_orders_html_renders_disposition_and_checklist():
    html = orders_html(_sample_results())
    assert "Burn ICU" in html
    assert "IV access" in html
    assert "Lab" in html
    assert "TBSA &gt; 20%" in html or "TBSA > 20%" in html  # reason rendered
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderers.py -v
```

Expected: ImportError — `fluid_html`, `orders_html` not yet defined.

- [ ] **Step 3: Implement `fluid_html` and `orders_html`**

Append to `renderers.py`:

```python
# ── fluid tab ────────────────────────────────────────────────────────────────

def fluid_html(r: dict) -> str:
    fluid = r.get("fluid", {})
    brooke = r.get("brooke", {})
    p = r.get("patient", {})
    weight = p.get("weight", 0)

    total = fluid.get("total_24h_ml", 0)
    first8 = fluid.get("first_8h_ml", 0)
    rest = fluid.get("next_16h_ml", 0)
    rate1 = fluid.get("rate_first_8h_mlph", 0)
    rate2 = fluid.get("rate_next_16h_mlph", 0)
    lag = fluid.get("lag_status", "on_time")
    catchup = fluid.get("catchup_rate_mlph")
    rem = fluid.get("hours_remaining_first_8h", 8)
    hours_since = r.get("hours_since", 0)

    # Catch-up alert
    if lag == "catching_up" and catchup is not None:
        catchup_alert = f"""
        <div class="alert-warn">
          ⏱ <b>Tertinggal {hours_since:g} jam.</b> 8-jam pertama tinggal {rem:g} jam —
          naikkan rate ke <b>~{catchup:g} mL/jam</b> sampai catch-up.
        </div>
        """
    elif lag == "first_8h_passed":
        catchup_alert = """
        <div class="alert-warn">
          ⚠ <b>8-jam pertama sudah terlewat</b> — titrasi cairan sesuai urine
          output aktual (target 0.5–1 mL/kg/jam).
        </div>
        """
    else:
        catchup_alert = ""

    brooke_total = brooke.get("total_24h_ml", 0)
    weight_target = (
        f"{0.5 * weight:.0f}–{1.0 * weight:.0f} mL/jam"
        if weight else "—"
    )

    return f"""
    <div class="tab-section">
      <div class="card-primary">
        <div class="sec-label" style="color:#1E40AF">PARKLAND (Default)</div>
        <div class="big-num">{_fmt_int(total)} mL · Ringer Laktat · 24 jam</div>
        <div class="muted small">Rumus: 4 mL × {weight:g} kg × TBSA% · Target urine {weight_target}</div>
      </div>
    </div>

    <div class="tab-section">
      <div class="sec-label">📅 JADWAL PEMBERIAN</div>
      <div class="grid-2">
        <div class="card-soft">
          <div class="muted small">8 JAM PERTAMA</div>
          <div class="num-md">{_fmt_int(first8)} mL</div>
          <div class="muted small">@ {rate1:.1f} mL/jam · dari saat kejadian</div>
        </div>
        <div class="card-soft">
          <div class="muted small">16 JAM BERIKUTNYA</div>
          <div class="num-md">{_fmt_int(rest)} mL</div>
          <div class="muted small">@ {rate2:.1f} mL/jam</div>
        </div>
      </div>
      {catchup_alert}
    </div>

    <div class="tab-section">
      <div class="sec-label">📊 PERBANDINGAN FORMULA</div>
      <table class="form-compare">
        <thead><tr><th>Formula</th><th style="text-align:right">Total 24h</th><th>Cairan</th><th>Catatan</th></tr></thead>
        <tbody>
          <tr><td><b>Parkland</b> ⭐</td><td style="text-align:right;font-weight:700">{_fmt_int(total)} mL</td><td>RL</td><td class="muted">4 mL/kg/%</td></tr>
          <tr><td>Modified Brooke</td><td style="text-align:right">{_fmt_int(brooke_total)} mL</td><td>RL</td><td class="muted">2 mL/kg/%</td></tr>
          <tr><td>Galveston (peds)</td><td style="text-align:right" class="muted">— N/A —</td><td class="muted">—</td><td class="muted">untuk usia &lt; 14</td></tr>
        </tbody>
      </table>
    </div>
    """


# ── orders tab ───────────────────────────────────────────────────────────────

def orders_html(r: dict) -> str:
    disposition = r.get("disposition", "—")
    reasons = r.get("disposition_reasons", [])
    orders = r.get("orders", [])
    disp_color = _disposition_color(disposition)

    disp_bg = {
        "#DC2626": "#FEE2E2", "#EA580C": "#FFEDD5",
        "#2563EB": "#DBEAFE", "#16A34A": "#DCFCE7",
    }.get(disp_color, "#F1F5F9")

    reasons_html = "".join(
        f"<li>{escape(reason)}</li>" for reason in reasons
    ) or "<li class='muted'>—</li>"

    orders_html_items = "".join(
        f"<div class='order-item'>{'⚠' if o.startswith('⚠') else '☑'} {escape(o.lstrip('⚠ '))}</div>"
        for o in orders
    )

    return f"""
    <div class="tab-section">
      <div class="card-disp" style="background:{disp_bg};border-left-color:{disp_color}">
        <div class="sec-label" style="color:{disp_color}">DISPOSITION</div>
        <div class="big-num" style="color:{disp_color}">→ {escape(disposition)}</div>
        <ul class="reasons">{reasons_html}</ul>
      </div>
    </div>

    <div class="tab-section">
      <div class="sec-label">📋 INITIAL ORDERS CHECKLIST</div>
      <div class="orders-list">
        {orders_html_items}
      </div>
    </div>

    <div class="tab-section">
      <div class="sec-label">💊 PAIN & WOUND CARE</div>
      <div class="muted small">
        <b>Analgesia:</b> Morfin titrasi sesuai NRS · target NRS &lt; 4 ·
        re-evaluasi q5-10min<br>
        <b>Wound:</b> Silver sulfadiazine 1% topical untuk derajat 2 ·
        hydrogel/non-adherent untuk superficial · ganti dressing q24h
      </div>
    </div>
    """
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderers.py -v
```

Expected: all renderer tests so far pass.

- [ ] **Step 5: Commit**

```bash
git add renderers.py tests/test_renderers.py
git commit -m "feat(renderers): add fluid_html and orders_html"
```

---

## Task 6: Add `monitoring_html` and `education_html` to `renderers.py`

**Files:**
- Modify: `renderers.py` (append two functions)
- Modify: `tests/test_renderers.py` (append tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_renderers.py`:

```python
from renderers import monitoring_html, education_html


def test_monitoring_html_renders_three_milestones():
    html = monitoring_html(_sample_results())
    assert "0–8" in html or "0-8" in html
    assert "8–16" in html or "8-16" in html
    assert "16–24" in html or "16-24" in html


def test_monitoring_html_includes_warning():
    html = monitoring_html(_sample_results())
    assert "MAJOR BURN" in html


def test_education_html_renders_explanation_and_refs():
    html = education_html(_sample_results())
    assert "Pasien dewasa" in html
    assert "ABA Guidelines" in html
    assert "Parkland Baxter" in html


def test_education_html_falls_back_when_explanation_missing():
    r = _sample_results()
    r["rag_explanation"] = ""
    r["references"] = []
    html = education_html(r)
    assert "ABA" in html  # static fallback present
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderers.py -v
```

Expected: ImportError on `monitoring_html`, `education_html`.

- [ ] **Step 3: Implement `monitoring_html` and `education_html`**

Append to `renderers.py`:

```python
# ── monitoring tab ───────────────────────────────────────────────────────────

def monitoring_html(r: dict) -> str:
    fluid = r.get("fluid", {})
    rate1 = fluid.get("rate_first_8h_mlph", 0)
    rate2 = fluid.get("rate_next_16h_mlph", 0)
    warning = r.get("warning", "")

    warning_html = (
        f'<div class="alert-warn">⚠ <b>Warning klinis:</b> {escape(warning)}</div>'
        if warning else ""
    )

    return f"""
    <div class="tab-section">
      <div class="sec-label">📅 24h MONITORING TIMELINE</div>
      <ul class="timeline">
        <li class="tl-item tl-active">
          <div class="tl-dot tl-dot-active"></div>
          <div class="tl-time">0–8 JAM</div>
          <div class="tl-body">Rate {rate1:.0f} mL/jam · cek urine /1jam · GCS · vitals q15min</div>
        </li>
        <li class="tl-item">
          <div class="tl-dot"></div>
          <div class="tl-time">8–16 JAM</div>
          <div class="tl-body">Rate {rate2:.0f} mL/jam · titrasi sesuai UO 0.5-1 mL/kg/jam</div>
        </li>
        <li class="tl-item">
          <div class="tl-dot"></div>
          <div class="tl-time">16–24 JAM</div>
          <div class="tl-body">Recheck TBSA manual · ABG ulang · plan eskar/graft · gizi enteral early</div>
        </li>
      </ul>
      {warning_html}
    </div>
    """


# ── education tab ────────────────────────────────────────────────────────────

_FALLBACK_REFS = [
    "ABA Guidelines on Management of Acute Burns (2022)",
    "Parkland Formula — Baxter CR, 1974",
    "Lund-Browder Chart (age-adjusted)",
    "ATLS Burn Module 10ed",
]


def education_html(r: dict) -> str:
    explanation = r.get("rag_explanation") or (
        "(Penjelasan RAG tidak tersedia — referensi statis di bawah ini.)"
    )
    refs = r.get("references") or _FALLBACK_REFS

    refs_html = "".join(f"<li>{escape(ref)}</li>" for ref in refs)

    return f"""
    <div class="tab-section">
      <div class="sec-label">📝 PANDUAN MANAJEMEN (RAG)</div>
      <div class="rag-block">{escape(explanation)}</div>
    </div>

    <div class="tab-section">
      <div class="sec-label">📖 REFERENSI</div>
      <ul class="refs">{refs_html}</ul>
    </div>
    """
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderers.py -v
```

Expected: all renderer tests pass.

- [ ] **Step 5: Commit**

```bash
git add renderers.py tests/test_renderers.py
git commit -m "feat(renderers): add monitoring_html and education_html"
```

---

## Task 7: Refactor `analyze()` in `app.py` to new signature + dict-based results

**Files:**
- Modify: `app.py` — replace the existing `analyze()` function

This task only changes the orchestration function. The UI is rebuilt in Task 8.

- [ ] **Step 1: Write a smoke test that exercises the new `analyze()` with a stubbed Gemini**

Create `tests/test_analyze.py`:

```python
"""Smoke test for the refactored analyze() — verifies the 6-tuple shape."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_analyze_returns_six_html_strings(tmp_path):
    # Create a tiny dummy image file that PIL can open.
    from PIL import Image
    img_path = tmp_path / "burn.jpg"
    Image.new("RGB", (50, 50), color=(200, 100, 100)).save(img_path)

    fake_ai = {
        "burn_degree": "Second degree deep",
        "tbsa_percent": 22.5,
        "areas": ["dada anterior", "lengan kiri"],
        "description": "luka berbatas tegas",
        "confidence": "high",
    }

    fake_rag = {"explanation": "Pasien dewasa...", "references": ["ABA 2022"]}

    with patch("app.call_gemini_vision", return_value=fake_ai), \
         patch("app.get_rag_engine") as rag_mock:
        rag_mock.return_value.query.return_value = fake_rag
        from app import analyze
        result = analyze(
            image_path=str(img_path),
            age=25, weight=60, height=170, hours_since=1,
            mechanism="Thermal", inhalation=True,
            circumferential=False, comorbid=[],
        )

    assert isinstance(result, tuple)
    assert len(result) == 6
    banner, summary, fluid, orders, monitoring, education = result
    assert "22.5" in banner
    assert "Second degree deep" in summary
    assert "Parkland" in fluid
    assert "IV access" in orders
    assert "MONITORING" in monitoring or "0–8" in monitoring or "0-8" in monitoring
    assert "REFERENSI" in education or "ABA" in education


def test_analyze_handles_missing_image():
    from app import analyze
    result = analyze(
        image_path=None, age=25, weight=60, height=170, hours_since=1,
        mechanism="Thermal", inhalation=False, circumferential=False, comorbid=[],
    )
    assert len(result) == 6
    # First element (banner area) should mention the upload requirement
    assert "Upload" in result[0] or "foto" in result[0].lower()


def test_analyze_handles_gemini_failure(tmp_path):
    from PIL import Image
    img_path = tmp_path / "burn.jpg"
    Image.new("RGB", (50, 50), color=(150, 150, 150)).save(img_path)

    with patch("app.call_gemini_vision", return_value=None):
        from app import analyze
        result = analyze(
            image_path=str(img_path), age=25, weight=60, height=170,
            hours_since=1, mechanism="Thermal", inhalation=False,
            circumferential=False, comorbid=[],
        )
    assert len(result) == 6
    # Failure message should appear somewhere in the response
    combined = " ".join(result)
    assert "gagal" in combined.lower() or "fail" in combined.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_analyze.py -v
```

Expected: failure because the existing `analyze()` returns an 8-tuple and has a different signature.

- [ ] **Step 3: Replace the `analyze()` function in `app.py`**

In `app.py`, find the existing `analyze()` function (currently around lines 171–275). Replace it entirely with this new version:

```python
def analyze(image_path, age, weight, height, hours_since,
            mechanism, inhalation, circumferential, comorbid):
    """
    Orchestrate vision + calculator + triage + orders + RAG.
    Returns a 6-tuple of HTML strings: (banner, summary, fluid, orders,
    monitoring, education) — one for each gr.HTML output in the UI.
    """
    from calculator import (
        calculate_parkland, classify_burn_severity, get_warning_message,
        modified_brooke, mosteller_bsa, parkland_with_lag,
    )
    from triage import classify, red_flags
    from orders import build_checklist
    from renderers import (
        banner_html, summary_html, fluid_html, orders_html,
        monitoring_html, education_html,
    )

    def _empty_six(message: str) -> tuple:
        msg_html = f'<div class="alert-warn">{message}</div>'
        empty = '<div class="muted small">—</div>'
        return (msg_html, empty, empty, empty, empty, empty)

    # ── Validate inputs ──────────────────────────────────────────────────────
    if image_path is None:
        return _empty_six("⚠️ Upload foto luka bakar terlebih dahulu.")

    try:
        weight_f = float(weight) if weight is not None else 0.0
    except (TypeError, ValueError):
        weight_f = 0.0
    if weight_f <= 0:
        return _empty_six("⚠️ Masukkan berat badan pasien (kg).")

    try:
        age_i = int(age) if age is not None else 25
    except (TypeError, ValueError):
        age_i = 25

    try:
        height_f = float(height) if height not in (None, 0, "") else None
    except (TypeError, ValueError):
        height_f = None

    try:
        hours_since_f = float(hours_since) if hours_since is not None else 0.0
    except (TypeError, ValueError):
        hours_since_f = 0.0
    if hours_since_f < 0:
        hours_since_f = 0.0

    mechanism_s = str(mechanism) if mechanism else "Thermal"
    comorbid_list = list(comorbid) if comorbid else []
    inhalation_b = bool(inhalation)
    circumferential_b = bool(circumferential)

    # ── Image ────────────────────────────────────────────────────────────────
    try:
        image = load_and_resize_image(image_path)
    except Exception as e:
        return _empty_six(f"❌ Gagal membaca gambar: {e}")

    # ── Vision (Gemini) ──────────────────────────────────────────────────────
    ai = call_gemini_vision(image, age_i)
    if ai is None:
        return _empty_six(
            "⚠️ Semua model AI gagal menganalisis foto. "
            "Cek koneksi dan rate limit Gemini, lalu coba lagi dalam 1-2 menit."
        )

    tbsa = ai["tbsa_percent"]
    burn_degree = ai["burn_degree"]

    # ── Calculations ────────────────────────────────────────────────────────
    fluid = parkland_with_lag(weight_f, tbsa, hours_since_f)
    brooke = modified_brooke(weight_f, tbsa)
    bsa = mosteller_bsa(weight_f, height_f)
    severity = classify_burn_severity(tbsa)
    warning = get_warning_message(tbsa, age_i)

    # ── Triage + orders ─────────────────────────────────────────────────────
    disposition, disp_reasons = classify(
        tbsa=tbsa, age=age_i, mechanism=mechanism_s,
        inhalation=inhalation_b, circumferential=circumferential_b,
        comorbid=comorbid_list, burn_degree=burn_degree,
    )
    flags = red_flags(
        tbsa=tbsa, inhalation=inhalation_b,
        circumferential=circumferential_b, comorbid=comorbid_list,
    )
    order_list = build_checklist(
        tbsa=tbsa, weight_kg=weight_f, mechanism=mechanism_s,
        inhalation=inhalation_b, circumferential=circumferential_b,
    )

    # ── RAG ─────────────────────────────────────────────────────────────────
    rag_explanation, references = "", []
    try:
        engine = get_rag_engine()
        question = (
            f"Pasien usia {age_i} tahun, berat {weight_f}kg, luka bakar "
            f"{severity.lower()}, TBSA {tbsa:.1f}% ({burn_degree}). "
            "Apa prioritas manajemen dan monitoring cairan?"
        )
        rag_result = engine.query(question, tbsa, age_i)
        rag_explanation = rag_result.get("explanation", "")
        references = rag_result.get("references", [])
    except Exception as e:
        print(f"[WARN] RAG: {e}")
        rag_explanation = ""
        references = []

    # ── Build results dict and render ───────────────────────────────────────
    results = {
        "patient": {
            "age": age_i, "weight": weight_f, "height": height_f,
            "bsa_m2": bsa, "mechanism": mechanism_s,
        },
        "ai": {
            "burn_degree": burn_degree, "tbsa": tbsa,
            "areas": ai.get("areas", []),
            "description": ai.get("description", ""),
            "confidence": ai.get("confidence", "medium"),
        },
        "severity": severity,
        "fluid": fluid,
        "brooke": brooke,
        "disposition": disposition,
        "disposition_reasons": disp_reasons,
        "red_flags": flags,
        "orders": order_list,
        "rag_explanation": rag_explanation,
        "references": references,
        "warning": warning,
        "hours_since": hours_since_f,
    }

    return (
        banner_html(results),
        summary_html(results),
        fluid_html(results),
        orders_html(results),
        monitoring_html(results),
        education_html(results),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/test_analyze.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Run the full test suite to make sure nothing else broke**

```bash
pytest -v
```

Expected: all tests pass (existing + new from Tasks 1-7).

Note: existing `test_smoke.py` may call the *old* `analyze()` signature. If so, it will fail and needs to be updated to match the new signature in this same task. Open it and update any positional/keyword calls accordingly.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_analyze.py tests/test_smoke.py
git commit -m "refactor(app): analyze() returns 6-tuple HTML, accepts 9 inputs"
```

---

## Task 8: Rebuild `build_ui()` in `app.py` — banner + 5 tabs + new CSS

**Files:**
- Modify: `app.py` — replace the `build_ui()` function and `CSS` constant

- [ ] **Step 1: Replace the `CSS` constant in `app.py`**

Find the `CSS = """..."""` block (currently around lines 282–304) and replace it with:

```python
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
*,body,.gradio-container{font-family:'Inter','Segoe UI',Arial,sans-serif!important}
body,.gradio-container{background:#F1F5F9!important;color:#1E293B!important}

/* Header */
.hdr{background:linear-gradient(135deg,#1D4ED8,#1E40AF);border-radius:12px;
     padding:22px 28px;margin-bottom:14px}
.hdr h1{font-size:1.6rem;font-weight:700;color:#fff!important;margin:0 0 4px 0}
.hdr p{color:#BFDBFE!important;margin:0;font-size:.82rem;line-height:1.6}

/* Section labels */
.sec{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;
     color:#1D4ED8;padding-bottom:5px;border-bottom:2px solid #DBEAFE;margin:16px 0 10px}
.sec-label{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;
           color:#1D4ED8;margin-bottom:6px}

/* Inputs */
.gradio-container label{color:#475569!important;font-size:.78rem!important;font-weight:600!important}
.gradio-container textarea,.gradio-container input[type=number],
.gradio-container input[type=text],.gradio-container select{
    background:#fff!important;border:1px solid #CBD5E1!important;
    color:#1E293B!important;border-radius:6px!important;font-size:.88rem!important}

/* Submit button */
.btn button{background:#1D4ED8!important;color:#fff!important;font-weight:700!important;
    font-size:.95rem!important;border-radius:7px!important;border:none!important;
    padding:13px!important;width:100%!important;
    box-shadow:0 2px 12px rgba(29,78,216,.35)!important}
.btn button:hover{background:#1E40AF!important}

/* KPI banner */
.kpi-banner{background:#fff;border:1px solid #1D4ED8;border-left:5px solid #1D4ED8;
            border-radius:8px;padding:14px 18px;margin-bottom:10px}
.kpi-label{font-size:.6rem;color:#1D4ED8;text-transform:uppercase;font-weight:700;
           letter-spacing:1.5px;margin-bottom:8px}
.kpi-grid{display:grid;grid-template-columns:1.4fr 1fr 1.2fr 1fr 1.3fr;gap:14px}
.kpi-tile{}
.kpi-key{font-size:.62rem;color:#64748B;font-weight:600;letter-spacing:.5px;text-transform:uppercase}
.kpi-val{font-size:.95rem;font-weight:700;color:#1E293B;line-height:1.15;margin-top:2px}
.kpi-big{font-size:1.4rem!important}
.kpi-sub{font-size:.7rem;color:#64748B;margin-top:1px}

/* Tab sections */
.tab-section{margin-bottom:14px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:6px 14px;font-size:.82rem;line-height:1.6}
.muted{color:#64748B}
.small{font-size:.74rem}

/* Cards */
.card-primary{background:#EFF6FF;border:1px solid #BFDBFE;border-left:4px solid #1D4ED8;
              border-radius:6px;padding:11px 14px}
.card-soft{background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px;padding:10px 12px}
.card-disp{border:1px solid;border-left:4px solid;border-radius:6px;padding:11px 14px}
.big-num{font-size:.95rem;font-weight:700;color:#1E293B;margin-top:3px}
.num-md{font-size:1rem;font-weight:700}
.reasons{margin:6px 0 0 18px;font-size:.78rem;color:#475569;line-height:1.6}

/* Confidence bar */
.conf-row{display:flex;align-items:center;gap:10px;font-size:.82rem}
.conf-bar{flex:1;background:#F1F5F9;height:9px;border-radius:5px;overflow:hidden}
.conf-fill{height:100%;border-radius:5px}

/* Red flag chips */
.flag-row{display:flex;flex-wrap:wrap;gap:5px}
.flag-chip{padding:4px 10px;border-radius:99px;font-size:.78rem;font-weight:600}
.flag-clear{font-weight:400!important}

/* Orders list */
.orders-list{font-size:.82rem;line-height:1.85}
.order-item{padding:1px 0}

/* Formula compare table */
.form-compare{width:100%;border-collapse:collapse;font-size:.8rem}
.form-compare thead{background:#F1F5F9}
.form-compare th{text-align:left;padding:6px 8px;border-bottom:2px solid #CBD5E1}
.form-compare td{padding:5px 8px;border-bottom:1px solid #E2E8F0}

/* Timeline */
.timeline{list-style:none;padding:0 0 0 18px;margin:0;border-left:2px solid #DBEAFE}
.tl-item{position:relative;padding-bottom:10px}
.tl-dot{position:absolute;left:-23px;top:2px;width:8px;height:8px;background:#fff;
        border:2px solid #1D4ED8;border-radius:50%}
.tl-dot-active{background:#1D4ED8;box-shadow:0 0 0 2px #1D4ED8}
.tl-active .tl-time{color:#1E40AF}
.tl-time{font-size:.82rem;font-weight:700;color:#475569}
.tl-body{font-size:.78rem;color:#475569;margin-top:2px}

/* RAG block */
.rag-block{background:#F8FAFC;border-radius:6px;padding:10px 12px;
           font-size:.82rem;line-height:1.7;color:#1E293B;white-space:pre-wrap}
.refs{margin:0 0 0 18px;font-size:.78rem;color:#475569;line-height:1.7}

/* Alerts */
.alert-warn{background:#FFF7ED;border:1px solid #FED7AA;border-radius:5px;
            padding:8px 11px;font-size:.78rem;color:#92400E;margin-top:6px}

/* Hint card */
.hint{background:#EFF6FF;border:1px solid #BFDBFE;border-left:4px solid #1D4ED8;
      border-radius:7px;padding:10px 13px;font-size:.78rem;color:#1E40AF;line-height:1.7;margin-top:10px}

/* Risk checkbox cards */
.risk-card label{background:#FFF7ED!important;border:1px solid #FED7AA!important;
                 padding:6px 8px!important;border-radius:5px!important;
                 color:#92400E!important;display:block!important;margin-bottom:5px!important}

/* Footer */
.ftr{text-align:center;color:#94A3B8;font-size:.74rem;margin-top:22px;
     padding:14px;border-top:1px solid #E2E8F0}
"""
```

- [ ] **Step 2: Replace the `build_ui()` function**

Find `build_ui()` (currently around lines 307–374) and replace with:

```python
def build_ui():
    with gr.Blocks(title="Sistem Penilaian Luka Bakar") as demo:
        gr.HTML("""
        <div class="hdr">
          <h1>🏥 Sistem Penilaian Luka Bakar</h1>
          <p>Clinical Decision Aid · Lund-Browder · Parkland · ABA Burn Center Criteria</p>
        </div>""")

        with gr.Row(equal_height=False):
            # ── Sidebar (left) ──────────────────────────────────────────────
            with gr.Column(scale=1, min_width=340):
                gr.HTML('<p class="sec">📷 Foto Luka Bakar</p>')
                img_in = gr.Image(type="filepath", label="Upload Foto", height=220)

                gr.HTML('<p class="sec">👤 Data Pasien</p>')
                with gr.Row():
                    age_in = gr.Number(value=25, label="Usia (th)",
                                       minimum=0, maximum=120, precision=0)
                    wt_in = gr.Number(value=60, label="Berat (kg)",
                                      minimum=1, maximum=300, precision=1)
                with gr.Row():
                    ht_in = gr.Number(value=None, label="Tinggi (cm) — opt",
                                      minimum=30, maximum=250, precision=1)
                    hrs_in = gr.Number(value=1, label="Jam sejak luka",
                                       minimum=0, maximum=72, precision=1)

                gr.HTML('<p class="sec">⚕️ Mekanisme & Risiko</p>')
                mech_in = gr.Dropdown(
                    choices=["Thermal", "Electrical", "Chemical"],
                    value="Thermal", label="Mekanisme cedera",
                )
                with gr.Group(elem_classes=["risk-card"]):
                    inhal_in = gr.Checkbox(label="Suspek inhalation injury (face/neck burn, hoarse, soot)")
                    circ_in = gr.Checkbox(label="Circumferential burn (melilit ekstremitas / dada)")
                comorb_in = gr.CheckboxGroup(
                    choices=["DM", "CKD", "Jantung", "Hamil"],
                    value=[], label="Komorbid (opt)",
                )

                with gr.Row(elem_classes=["btn"]):
                    btn = gr.Button("🔍  Analisis Luka Bakar", variant="primary")

                gr.HTML("""
                <div class="hint">
                  <b>Petunjuk:</b><br>
                  1. Upload foto luka bakar yang jelas<br>
                  2. Isi data pasien & mekanisme<br>
                  3. Klik <em>Analisis</em> · tunggu 15-60 detik<br>
                  4. Jika gagal, klik sekali lagi<br>
                  <br>
                  <em>Jam sejak luka</em> dipakai untuk menghitung catch-up rate Parkland bila pasien datang terlambat.
                </div>""")

            # ── Output area (right) ─────────────────────────────────────────
            with gr.Column(scale=2, min_width=520):
                banner_out = gr.HTML(value='<div class="kpi-banner"><div class="kpi-label">PATIENT BANNER · KPI</div><div class="muted small">Hasil akan tampil setelah Analisis.</div></div>')

                with gr.Tabs():
                    with gr.Tab("📊 Ringkasan"):
                        summary_out = gr.HTML(value='<div class="muted small">Belum ada hasil.</div>')
                    with gr.Tab("💧 Cairan"):
                        fluid_out = gr.HTML(value='<div class="muted small">Belum ada hasil.</div>')
                    with gr.Tab("📋 Orders"):
                        orders_out = gr.HTML(value='<div class="muted small">Belum ada hasil.</div>')
                    with gr.Tab("⏱ Monitoring"):
                        monitoring_out = gr.HTML(value='<div class="muted small">Belum ada hasil.</div>')
                    with gr.Tab("📚 Edukasi & Refs"):
                        education_out = gr.HTML(value='<div class="muted small">Belum ada hasil.</div>')

        gr.HTML("""
        <div class="ftr">
          Sistem Penilaian Luka Bakar · Lund-Browder · Parkland (Baxter, 1974) · ABA Criteria<br>
          Alat bantu klinis — keputusan akhir tetap pada tenaga medis.
        </div>""")

        btn.click(
            fn=analyze,
            inputs=[img_in, age_in, wt_in, ht_in, hrs_in,
                    mech_in, inhal_in, circ_in, comorb_in],
            outputs=[banner_out, summary_out, fluid_out,
                     orders_out, monitoring_out, education_out],
            show_progress=True,
        )

    return demo
```

- [ ] **Step 3: Verify the app starts and renders**

```bash
cd /Users/irhammohammad/Documents/Code/Random/MedAssistant/burn_assessment_web
source venv/bin/activate
python app.py
```

Expected: server starts on `http://0.0.0.0:7860`. Open it in a browser and confirm:
- Header gradient renders
- Left sidebar shows photo upload, 4 numeric fields, dropdown, 2 checkboxes, comorbid group, button
- Right side shows empty banner + 5 tabs
- No console errors

Stop with Ctrl+C.

- [ ] **Step 4: Run the test suite once more**

```bash
pytest -v
```

Expected: all tests still pass.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat(ui): rebuild UI with KPI banner, 5 tabs, expanded CSS"
```

---

## Task 9: End-to-end manual verification + push to HF Spaces

**Files:** none (verification + deploy).

- [ ] **Step 1: Run the app and exercise a full flow**

```bash
source venv/bin/activate
python app.py
```

In the browser:

1. Upload a burn photo (any photo for smoke; use a real one for credibility).
2. Set: Usia 25, BB 60, Tinggi 170, Jam sejak luka 1, Mekanisme Thermal, Inhalation ON, Circumferential OFF, Komorbid empty.
3. Click *Analisis Luka Bakar*. Wait 15-60s for Gemini.
4. Confirm:
   - Banner shows 5 tiles populated
   - Tab Ringkasan: AI detection, confidence bar, red-flag chips (Inhalation = active red, others gray)
   - Tab Cairan: Parkland card, schedule, **catch-up alert visible** (because hours_since=1), formula table
   - Tab Orders: Disposition red (ICU), checklist with Intubasi-ready item, pain & wound section
   - Tab Monitoring: 3-milestone timeline, warning box
   - Tab Edukasi: RAG explanation + references

5. Stop the server (Ctrl+C).

- [ ] **Step 2: Run pytest one last time**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Push to HF Space**

```bash
git push hf main:main
```

Expected: HF rebuilds the Space (2–5 minutes). Check `https://huggingface.co/spaces/Lamiore/MedTen` build logs.

- [ ] **Step 4: Verify the deployed Space**

Visit `https://Lamiore-MedTen.hf.space` and repeat the smoke test from Step 1 against the deployed Space. If anything fails, check Space logs and iterate.

- [ ] **Step 5: Final commit (if any tweaks were needed during deploy)**

If everything works without deploy-time fixes, no extra commit is needed. The Task 8 commit is the deploy-completing commit.

---

## Self-Review

**Spec coverage check** — every spec section maps to at least one task:

| Spec section | Implementing task(s) |
|---|---|
| 1. Audience & Goals | 8 (visual direction lives in CSS) |
| 2. Layout | 8 |
| 3. Input Form | 8 |
| 4. KPI Banner | 4 |
| 5.1 Tab Ringkasan | 4 |
| 5.2 Tab Cairan | 1 (parkland_with_lag, modified_brooke), 5 (fluid_html) |
| 5.3 Tab Orders | 2 (triage), 3 (orders), 5 (orders_html) |
| 5.4 Tab Monitoring | 6 (monitoring_html) |
| 5.5 Tab Edukasi & Refs | 6 (education_html) |
| 6. Code Structure | 1–8 (all create/extend) |
| 7. Data Flow | 7 (analyze) |
| 8. Error Handling & Edge Cases | 7 (analyze short-circuits + per-renderer fallbacks) |
| 9. Testing | 1–7 |
| 10. Out of Scope | (intentionally omitted) |

No gaps.

**Placeholder scan:** No TBDs, no "implement later", no vague "handle edge cases" — every step has actual code or an exact command. Renderers list every conditional path.

**Type/name consistency:** The results dict shape is defined in Task 4 (`_sample_results()`) and consumed identically in Tasks 5, 6, 7. Function names match their tests. `analyze()` returns 6-tuple HTML in both Task 7 implementation and Task 8 UI wiring.

Done — ready for execution handoff.
