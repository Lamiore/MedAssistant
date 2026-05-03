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
