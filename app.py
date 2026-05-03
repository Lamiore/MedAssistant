"""
app.py — Burn Assessment Web (HF Spaces single-file entry point).

Contains:
- parse_gemini_json: parse Gemini's JSON response
- call_gemini_vision: invoke Gemini API with image (added in T7)
- analyze: orchestrate vision + calculator + RAG (added in T7)
- build_ui: Gradio UI definition (added in T8)

Entry: `python app.py` launches Gradio on port 7860.
"""
import io
import json
import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

from calculator import (
    calculate_parkland,
    classify_burn_severity,
    get_warning_message,
)
from rag_engine import RAGEngine

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

VISION_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

# Permissive safety settings for medical imagery (burns can look graphic)
SAFETY_SETTINGS = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
]

# Lazy-init RAG engine (built once on first request)
_rag_engine = None


def get_rag_engine():
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine()
    return _rag_engine

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


# ── Image preprocessing ──────────────────────────────────────────────────────

def load_and_resize_image(image_path: str, max_px: int = 1024) -> Image.Image:
    """Open image from path and downsize for API efficiency."""
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    return img


# ── Gemini vision call ───────────────────────────────────────────────────────

def call_gemini_vision(image: Image.Image, age: int):
    """Call Gemini with image + structured-output prompt. Returns parsed dict or None."""
    prompt = (
        "Analyze this burn wound image. Patient age: "
        f"{age} years.\n"
        "Reply ONLY with valid JSON (no markdown, no extra text) in this exact schema:\n"
        '{\n'
        '  "burn_degree": "First degree" | "Second degree superficial" | "Second degree deep" | "Third degree",\n'
        '  "tbsa_percent": <number 0-100>,\n'
        '  "areas": ["list of body parts affected"],\n'
        '  "description": "brief wound description",\n'
        '  "confidence": "low" | "medium" | "high"\n'
        '}\n'
        "Only count 2nd-degree and 3rd-degree burns toward tbsa_percent. "
        "1st-degree (red, no blisters) does NOT count."
    )

    config = types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=512,
        response_mime_type="application/json",
        safety_settings=SAFETY_SETTINGS,
    )

    for model_name in VISION_MODELS:
        try:
            print(f"[VISION] Trying {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, image],
                config=config,
            )
            raw = (response.text or "").strip()

            parsed = parse_gemini_json(raw)
            if parsed:
                print(f"[VISION] OK {model_name} TBSA={parsed['tbsa_percent']}%")
                return parsed

            print(f"[WARN] {model_name}: unparseable response")
        except Exception as e:
            print(f"[WARN] {model_name}: {e}")
            time.sleep(1)

    return None


# ── Main orchestrator ────────────────────────────────────────────────────────

def analyze(image_path, age, weight):
    """Called by Gradio. Returns 8-tuple of strings for the output components."""
    if image_path is None:
        return ("⚠️ Upload foto luka bakar terlebih dahulu.",) + ("",) * 7

    try:
        weight = float(weight)
    except (TypeError, ValueError):
        weight = 0.0
    if weight <= 0:
        return ("⚠️ Masukkan berat badan pasien (kg).",) + ("",) * 7

    try:
        age = int(age) if age is not None else 25
    except (TypeError, ValueError):
        age = 25

    try:
        image = load_and_resize_image(image_path)
    except Exception as e:
        return (f"❌ Gagal membaca gambar: {e}",) + ("",) * 7

    ai = call_gemini_vision(image, age)
    if ai is None:
        return (
            "⚠️ Semua model AI gagal menganalisis foto.\n\n"
            "Kemungkinan penyebab:\n"
            "• Rate limit Gemini API — tunggu 1-2 menit lalu coba lagi\n"
            "• Foto terlalu gelap atau tidak jelas\n"
            "• Koneksi internet bermasalah\n\n"
            "Silakan klik tombol Analisis kembali.",
        ) + ("",) * 7

    tbsa = ai["tbsa_percent"]
    degree = ai["burn_degree"]
    areas = ai["areas"]
    desc = ai["description"]
    conf = ai["confidence"]

    fluid = calculate_parkland(weight, tbsa)
    severity = classify_burn_severity(tbsa)
    warning = get_warning_message(tbsa, age)

    rag_exp = ""
    refs = []
    try:
        engine = get_rag_engine()
        question = (
            f"Pasien usia {age} tahun, berat {weight}kg, luka bakar "
            f"{severity.lower()}, TBSA {tbsa:.1f}% ({degree}). "
            "Apa prioritas manajemen dan monitoring cairan?"
        )
        result = engine.query(question, tbsa, age)
        rag_exp = result.get("explanation", "")
        refs = result.get("references", [])
    except Exception as e:
        print(f"[WARN] RAG: {e}")
        rag_exp = "(RAG explanation unavailable — see references below.)"

    icon = {
        "Minor": "🟢",
        "Moderate": "🟡",
        "Major / Severe": "🔴",
        "Critical / Life-Threatening": "🚨",
    }.get(severity, "⚪")

    tbsa_str = (
        f"TBSA           : {tbsa:.1f}%\n"
        f"Area terbakar  : {', '.join(areas) if areas else '-'}\n"
        f"Karakteristik  : {desc}\n"
        f"Kepercayaan AI : {conf.upper()}"
    )
    fluid_str = (
        f"Total 24 jam : {fluid['total_24h_ml']:,.0f} mL {fluid['fluid_type']}\n"
        f"Target urine : {0.5 * weight:.0f} – {1.0 * weight:.0f} mL/jam\n"
        f"Rumus        : 4 mL × {weight:.0f} kg × {tbsa:.1f}% = {fluid['total_24h_ml']:,.0f} mL"
    )
    sched_str = (
        f"8 JAM PERTAMA  (dari saat kejadian)\n"
        f"  Volume : {fluid['first_8h_ml']:,.0f} mL   |   Rate : {fluid['rate_first_8h_mlph']:.1f} mL/jam\n\n"
        f"16 JAM BERIKUTNYA\n"
        f"  Volume : {fluid['next_16h_ml']:,.0f} mL   |   Rate : {fluid['rate_next_16h_mlph']:.1f} mL/jam\n\n"
        f"Waktu dihitung dari SAAT KEJADIAN, bukan masuk RS!\n"
        f"Titrasi sesuai urine output aktual."
    )
    refs_str = (
        "\n".join(f"• {x}" for x in refs)
        if refs
        else (
            "• Parkland Formula (Baxter CR, 1974)\n"
            "• Lund-Browder Chart\n"
            "• ABA Guidelines on Management of Acute Burns (2022)"
        )
    )

    return (
        tbsa_str,
        degree,
        f"{icon}  {severity}",
        fluid_str,
        sched_str,
        rag_exp,
        refs_str,
        warning,
    )
