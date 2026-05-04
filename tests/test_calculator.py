"""Sanity tests for calculator.py — verify the byte-for-byte copy still works."""
import sys
from pathlib import Path

# Make parent directory importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from calculator import (
    calculate_parkland,
    classify_burn_severity,
    get_warning_message,
    calculate_tbsa_lund_browder,
)


def test_parkland_basic():
    # 70 kg patient with 20% TBSA: 4 * 70 * 20 = 5600 mL
    result = calculate_parkland(70, 20)
    assert result["total_24h_ml"] == 5600.0
    assert result["first_8h_ml"] == 2800.0
    assert result["next_16h_ml"] == 2800.0
    assert result["fluid_type"] == "Ringer's Lactate"
    assert result["rate_first_8h_mlph"] == 350.0


def test_severity_thresholds():
    assert classify_burn_severity(5) == "Minor"
    assert classify_burn_severity(15) == "Moderate"
    assert classify_burn_severity(25) == "Major / Severe"
    assert classify_burn_severity(50) == "Critical / Life-Threatening"


def test_warning_critical():
    msg = get_warning_message(45, 30)
    assert "CRITICAL" in msg


def test_warning_pediatric():
    msg = get_warning_message(15, 5)
    assert "PEDIATRIC" in msg


def test_warning_none_for_minor():
    msg = get_warning_message(5, 30)
    assert msg == ""


def test_tbsa_adult_full_anterior_trunk():
    # Adult: anterior trunk fully burned = 13%
    tbsa = calculate_tbsa_lund_browder(30, {"anterior_trunk": 100})
    assert tbsa == 13.0


def test_tbsa_infant_head_larger():
    # Infant (age 0): head should be ~19% (head_half 9.5 * 2)
    tbsa = calculate_tbsa_lund_browder(0, {"head": 100})
    assert tbsa == 19.0


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
