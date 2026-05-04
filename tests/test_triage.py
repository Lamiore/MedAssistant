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
    # tbsa=7 falls in the 5–10% range: no ABA criterion fires, ward disposition.
    disposition, reasons = classify(**_kwargs(tbsa=7.0))
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
