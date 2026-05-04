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
