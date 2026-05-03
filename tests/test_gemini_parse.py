"""Unit tests for the Gemini response parser."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import parse_gemini_json


def test_parse_clean_json():
    raw = '{"burn_degree":"Second degree superficial","tbsa_percent":15,"areas":["forearm"],"description":"red blistered","confidence":"high"}'
    result = parse_gemini_json(raw)
    assert result["burn_degree"] == "Second degree superficial"
    assert result["tbsa_percent"] == 15
    assert result["areas"] == ["forearm"]
    assert result["confidence"] == "high"


def test_parse_strips_markdown_fences():
    raw = '```json\n{"burn_degree":"Third degree","tbsa_percent":30,"areas":[],"description":"x","confidence":"low"}\n```'
    result = parse_gemini_json(raw)
    assert result["burn_degree"] == "Third degree"
    assert result["tbsa_percent"] == 30


def test_parse_clamps_tbsa_to_range():
    """Reject TBSA values outside 0-100 — clamp."""
    raw = '{"burn_degree":"Second degree","tbsa_percent":150,"areas":[],"description":"x","confidence":"low"}'
    result = parse_gemini_json(raw)
    assert 0 <= result["tbsa_percent"] <= 100


def test_parse_missing_fields_defaults():
    """Missing fields get safe defaults, not crash."""
    raw = '{"burn_degree":"Second degree","tbsa_percent":10}'
    result = parse_gemini_json(raw)
    assert result["areas"] == []
    assert result["description"] == ""
    assert result["confidence"] == "medium"


def test_parse_invalid_json_returns_none():
    raw = 'this is not json at all'
    result = parse_gemini_json(raw)
    assert result is None


def test_parse_handles_extra_text_around_json():
    raw = 'Sure, here is the analysis:\n{"burn_degree":"First degree","tbsa_percent":2,"areas":["hand"],"description":"red","confidence":"high"}\nLet me know if you need more.'
    result = parse_gemini_json(raw)
    assert result is not None
    assert result["burn_degree"] == "First degree"
