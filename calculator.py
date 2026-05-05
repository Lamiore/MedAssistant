"""
calculator.py
=============
Burn Assessment Calculator
- Lund-Browder chart (age-adjusted TBSA calculation)
- Parkland Formula for fluid resuscitation
- Burn severity classification
"""

import math

# ─────────────────────────────────────────────
# Lund-Browder Age-Dependent Table (% per area)
# ─────────────────────────────────────────────
# Head total = Area A × 2 (half-head × 2)
# Thigh      = Area B × 2 (half-thigh × 2, per leg)
# Lower leg  = Area C × 2 (half-lower-leg × 2, per leg)

LUND_BROWDER_AGE_DEPENDENT = {
    # format: age_key -> {area: percentage}
    # area keys: 'head_half', 'thigh_half', 'lower_leg_half'
    0:     {"head_half": 9.5,  "thigh_half": 2.75, "lower_leg_half": 2.5},
    1:     {"head_half": 8.5,  "thigh_half": 3.25, "lower_leg_half": 2.5},
    5:     {"head_half": 6.5,  "thigh_half": 4.0,  "lower_leg_half": 2.75},
    10:    {"head_half": 5.5,  "thigh_half": 4.25, "lower_leg_half": 3.0},
    15:    {"head_half": 4.5,  "thigh_half": 4.5,  "lower_leg_half": 3.25},
    999:   {"head_half": 4.5,  "thigh_half": 4.75, "lower_leg_half": 3.5},  # adult
}

# Fixed areas (age-independent), in percent
FIXED_AREAS = {
    "neck":               2.0,
    "anterior_trunk":     13.0,
    "posterior_trunk":    13.0,
    "right_upper_arm":    4.0,
    "left_upper_arm":     4.0,
    "right_forearm":      3.0,
    "left_forearm":       3.0,
    "right_hand":         2.5,
    "left_hand":          2.5,
    "genitalia":          1.0,
    "right_foot":         3.5,
    "left_foot":          3.5,
}

# Variable areas (derived from age-dependent table, full area = half × 2)
VARIABLE_AREA_KEYS = {
    "head":           ("head_half", 2),        # entire head
    "right_thigh":    ("thigh_half", 2),       # full right thigh
    "left_thigh":     ("thigh_half", 2),       # full left thigh
    "right_lower_leg":("lower_leg_half", 2),   # full right lower leg
    "left_lower_leg": ("lower_leg_half", 2),   # full left lower leg
}


def _get_age_key(age: int) -> int:
    """Return the nearest lower bracket from LUND_BROWDER_AGE_DEPENDENT for given age."""
    brackets = sorted([k for k in LUND_BROWDER_AGE_DEPENDENT.keys() if k != 999])
    selected = brackets[0]
    for b in brackets:
        if age >= b:
            selected = b
    if age >= 15:
        return 999  # adult
    return selected


def _get_area_percent(area_key: str, age: int) -> float:
    """
    Return the percentage for a given body area key, adjusted for age.
    Returns 0.0 if area_key is not recognized.
    """
    # Fixed areas
    if area_key in FIXED_AREAS:
        return FIXED_AREAS[area_key]

    # Variable areas
    if area_key in VARIABLE_AREA_KEYS:
        table_key, multiplier = VARIABLE_AREA_KEYS[area_key]
        age_key = _get_age_key(age)
        half_val = LUND_BROWDER_AGE_DEPENDENT[age_key][table_key]
        return half_val * multiplier

    return 0.0


def calculate_tbsa_lund_browder(age: int, burned_areas: dict) -> float:
    """
    Hitung TBSA berdasarkan Lund-Browder chart disesuaikan usia.

    Parameters
    ----------
    age : int
        Usia pasien dalam tahun.
    burned_areas : dict
        Dictionary area tubuh yang terbakar beserta persentase keterlibatannya (0–100%).
        Contoh:
            {
                "head": 100,        # kepala terbakar 100%
                "anterior_trunk": 50,  # trunk anterior terbakar 50%
                "right_upper_arm": 100
            }
        Hanya derajat 2 dan 3 yang dimasukkan ke sini.

    Returns
    -------
    float
        Total TBSA (%) — hanya derajat 2 dan 3.
    """
    total = 0.0
    for area_key, involvement_pct in burned_areas.items():
        area_pct = _get_area_percent(area_key, age)
        contribution = area_pct * (involvement_pct / 100.0)
        total += contribution
    return round(total, 2)


def calculate_parkland(weight_kg: float, tbsa_percent: float) -> dict:
    """
    Parkland Formula: 4 mL × weight(kg) × TBSA(%)

    Parameters
    ----------
    weight_kg : float
        Berat badan pasien dalam kg.
    tbsa_percent : float
        Persentase TBSA (hanya derajat 2 dan 3).

    Returns
    -------
    dict with keys:
        total_24h_ml        – total cairan 24 jam (mL)
        first_8h_ml         – cairan 8 jam pertama (mL)
        next_16h_ml         – cairan 16 jam berikutnya (mL)
        fluid_type          – jenis cairan
        rate_first_8h_mlph  – kecepatan tetes 8 jam pertama (mL/jam)
        rate_next_16h_mlph  – kecepatan tetes 16 jam berikutnya (mL/jam)
    """
    total = 4.0 * weight_kg * tbsa_percent
    first_half = total / 2.0
    second_half = total / 2.0

    return {
        "total_24h_ml":        round(total, 2),
        "first_8h_ml":         round(first_half, 2),
        "next_16h_ml":         round(second_half, 2),
        "fluid_type":          "Ringer's Lactate",
        "rate_first_8h_mlph":  round(first_half / 8.0, 2),
        "rate_next_16h_mlph":  round(second_half / 16.0, 2),
    }


def classify_burn_severity(tbsa: float) -> str:
    """
    Klasifikasi keparahan luka bakar berdasarkan TBSA.

    Parameters
    ----------
    tbsa : float
        Total TBSA (%).

    Returns
    -------
    str
        Klasifikasi keparahan.
    """
    if tbsa > 40.0:
        return "Critical / Life-Threatening"
    elif tbsa > 20.0:
        return "Major / Severe"
    elif tbsa >= 10.0:
        return "Moderate"
    else:
        return "Minor"


def get_warning_message(tbsa: float, age: int) -> str:
    """
    Buat pesan peringatan klinis berdasarkan TBSA dan usia.

    Returns
    -------
    str or None
        Pesan peringatan, atau string kosong jika tidak ada.
    """
    warnings = []
    if tbsa > 40:
        warnings.append(
            "⚠️ CRITICAL: TBSA > 40% — Risiko mortalitas sangat tinggi. "
            "Pertimbangkan transfer ke pusat luka bakar tersier segera."
        )
    elif tbsa > 20:
        warnings.append(
            "⚠️ MAJOR BURN: TBSA > 20% — Pasien memerlukan perawatan di unit luka bakar. "
            "Monitor urine output ketat (target 0.5 mL/kg/jam dewasa)."
        )
    if age < 10 and tbsa > 10:
        warnings.append(
            "⚠️ PEDIATRIC: Anak < 10 tahun dengan TBSA > 10% — "
            "Pertimbangkan Galveston formula dan tambahkan cairan maintenance D5LR. "
            "Monitor glukosa setiap 2–4 jam."
        )
    if age > 50 and tbsa > 10:
        warnings.append(
            "⚠️ GERIATRIC: Pasien > 50 tahun dengan TBSA > 10% — "
            "Risiko komplikasi meningkat signifikan. Refer ke burn center."
        )
    return " | ".join(warnings) if warnings else ""


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
    base = dict(calculate_parkland(weight_kg, tbsa_percent))
    if hours_since <= 0:
        base["catchup_rate_mlph"] = base["rate_first_8h_mlph"]
        base["hours_remaining_first_8h"] = 8.0
        base["lag_status"] = "on_time"
    elif hours_since < 8:
        remaining = 8 - hours_since
        base["catchup_rate_mlph"] = round(base["first_8h_ml"] / remaining, 2)
        base["hours_remaining_first_8h"] = float(remaining)
        base["lag_status"] = "catching_up"
    else:
        base["catchup_rate_mlph"] = None
        base["hours_remaining_first_8h"] = 0.0
        base["lag_status"] = "first_8h_passed"
    return base
