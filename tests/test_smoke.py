"""Smoke tests — these hit real services (embedding model + Gemini).

Skip them if GEMINI_API_KEY is unset or still the placeholder.
"""
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))


def _no_real_key() -> bool:
    key = os.getenv("GEMINI_API_KEY", "")
    return not key or key == "your_key_here"


@pytest.mark.skipif(_no_real_key(), reason="GEMINI_API_KEY not set — skip live API tests")
def test_rag_engine_initializes_and_queries():
    """End-to-end: build index, run query, get explanation."""
    from rag_engine import RAGEngine

    engine = RAGEngine()
    result = engine.query(
        "Pasien usia 30 tahun, TBSA 25%. Apa prioritas manajemen?",
        tbsa=25.0,
        age=30,
    )

    assert "explanation" in result
    assert "references" in result
    assert len(result["explanation"]) > 50, "Explanation should be substantive"
    assert isinstance(result["references"], list)
    assert len(result["references"]) > 0
