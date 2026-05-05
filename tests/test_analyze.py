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
