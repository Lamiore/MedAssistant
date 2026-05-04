"""Tests for orders.py — conditional initial-orders checklist."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orders import build_checklist


def _kwargs(**overrides):
    base = dict(
        tbsa=15.0, age=30, weight_kg=60,
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
