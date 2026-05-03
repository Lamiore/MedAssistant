"""
app.py — Burn Assessment Web (HF Spaces single-file entry point).

Contains:
- parse_gemini_json: parse Gemini's JSON response
- call_gemini_vision: invoke Gemini API with image (added in T7)
- analyze: orchestrate vision + calculator + RAG (added in T7)
- build_ui: Gradio UI definition (added in T8)

Entry: `python app.py` launches Gradio on port 7860.
"""
import json
import re

# ── Gemini response parser ────────────────────────────────────────────────────

def parse_gemini_json(raw: str):
    """Extract and validate JSON from Gemini's response.

    Returns a dict with keys: burn_degree, tbsa_percent, areas, description,
    confidence. Returns None if the response cannot be parsed at all.
    """
    if not raw:
        return None

    # Strip markdown code fences if present
    cleaned = re.sub(r"```json\s*|```\s*", "", raw).strip()

    # Find the first {...} block (handles extra text around the JSON)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    # Apply safe defaults and clamp values
    tbsa = data.get("tbsa_percent", 0)
    try:
        tbsa = max(0.0, min(100.0, float(tbsa)))
    except (TypeError, ValueError):
        tbsa = 0.0

    return {
        "burn_degree": data.get("burn_degree", "Unknown"),
        "tbsa_percent": tbsa,
        "areas": data.get("areas", []) if isinstance(data.get("areas"), list) else [],
        "description": data.get("description", ""),
        "confidence": data.get("confidence", "medium"),
    }
