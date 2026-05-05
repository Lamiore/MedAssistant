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

def analyze(image_path, age, weight, height, hours_since,
            mechanism, inhalation, circumferential, comorbid):
    """
    Orchestrate vision + calculator + triage + orders + RAG.
    Returns a 6-tuple of HTML strings: (banner, summary, fluid, orders,
    monitoring, education) — one for each gr.HTML output in the UI.
    """
    from calculator import (
        calculate_parkland, classify_burn_severity, get_warning_message,
        modified_brooke, mosteller_bsa, parkland_with_lag,
    )
    from triage import classify, red_flags
    from orders import build_checklist
    from renderers import (
        banner_html, summary_html, fluid_html, orders_html,
        monitoring_html, education_html,
    )

    def _empty_six(message: str) -> tuple:
        msg_html = f'<div class="alert-warn">{message}</div>'
        empty = '<div class="muted kpi-hint">—</div>'
        return (msg_html, empty, empty, empty, empty, empty)

    # ── Validate inputs ──────────────────────────────────────────────────────
    if image_path is None:
        return _empty_six("⚠️ Upload foto luka bakar terlebih dahulu.")

    try:
        weight_f = float(weight) if weight is not None else 0.0
    except (TypeError, ValueError):
        weight_f = 0.0
    if weight_f <= 0:
        return _empty_six("⚠️ Masukkan berat badan pasien (kg).")

    try:
        age_i = int(age) if age is not None else 25
    except (TypeError, ValueError):
        age_i = 25

    try:
        height_f = float(height) if height not in (None, 0, "") else None
    except (TypeError, ValueError):
        height_f = None

    try:
        hours_since_f = float(hours_since) if hours_since is not None else 0.0
    except (TypeError, ValueError):
        hours_since_f = 0.0
    if hours_since_f < 0:
        hours_since_f = 0.0

    mechanism_s = str(mechanism) if mechanism else "Thermal"
    comorbid_list = list(comorbid) if comorbid else []
    inhalation_b = bool(inhalation)
    circumferential_b = bool(circumferential)

    # ── Image ────────────────────────────────────────────────────────────────
    try:
        image = load_and_resize_image(image_path)
    except Exception as e:
        return _empty_six(f"❌ Gagal membaca gambar: {e}")

    # ── Vision (Gemini) ──────────────────────────────────────────────────────
    ai = call_gemini_vision(image, age_i)
    if ai is None:
        return _empty_six(
            "⚠️ Semua model AI gagal menganalisis foto. "
            "Cek koneksi dan rate limit Gemini, lalu coba lagi dalam 1-2 menit."
        )

    tbsa = ai["tbsa_percent"]
    burn_degree = ai["burn_degree"]

    # ── Calculations ────────────────────────────────────────────────────────
    fluid = parkland_with_lag(weight_f, tbsa, hours_since_f)
    brooke = modified_brooke(weight_f, tbsa)
    bsa = mosteller_bsa(weight_f, height_f)
    severity = classify_burn_severity(tbsa)
    warning = get_warning_message(tbsa, age_i)

    # ── Triage + orders ─────────────────────────────────────────────────────
    disposition, disp_reasons = classify(
        tbsa=tbsa, age=age_i, mechanism=mechanism_s,
        inhalation=inhalation_b, circumferential=circumferential_b,
        comorbid=comorbid_list, burn_degree=burn_degree,
    )
    flags = red_flags(
        tbsa=tbsa, inhalation=inhalation_b,
        circumferential=circumferential_b, comorbid=comorbid_list,
    )
    order_list = build_checklist(
        tbsa=tbsa, weight_kg=weight_f, mechanism=mechanism_s,
        inhalation=inhalation_b, circumferential=circumferential_b,
    )

    # ── RAG ─────────────────────────────────────────────────────────────────
    rag_explanation, references = "", []
    try:
        engine = get_rag_engine()
        question = (
            f"Pasien usia {age_i} tahun, berat {weight_f}kg, luka bakar "
            f"{severity.lower()}, TBSA {tbsa:.1f}% ({burn_degree}). "
            "Apa prioritas manajemen dan monitoring cairan?"
        )
        rag_result = engine.query(question, tbsa, age_i)
        rag_explanation = rag_result.get("explanation", "")
        references = rag_result.get("references", [])
    except Exception as e:
        print(f"[WARN] RAG: {e}")
        rag_explanation = ""
        references = []

    # ── Build results dict and render ───────────────────────────────────────
    results = {
        "patient": {
            "age": age_i, "weight": weight_f, "height": height_f,
            "bsa_m2": bsa, "mechanism": mechanism_s,
        },
        "ai": {
            "burn_degree": burn_degree, "tbsa": tbsa,
            "areas": ai.get("areas", []),
            "description": ai.get("description", ""),
            "confidence": ai.get("confidence", "medium"),
        },
        "severity": severity,
        "fluid": fluid,
        "brooke": brooke,
        "disposition": disposition,
        "disposition_reasons": disp_reasons,
        "red_flags": flags,
        "orders": order_list,
        "rag_explanation": rag_explanation,
        "references": references,
        "warning": warning,
        "hours_since": hours_since_f,
    }

    return (
        banner_html(results),
        summary_html(results),
        fluid_html(results),
        orders_html(results),
        monitoring_html(results),
        education_html(results),
    )


# ── Gradio UI ────────────────────────────────────────────────────────────────

import gradio as gr  # noqa: E402 (imported here to keep top-of-file lean)

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
*,body,.gradio-container{font-family:'Inter','Segoe UI',Arial,sans-serif!important}
body,.gradio-container{background:#F1F5F9!important;color:#1E293B!important}
.hdr{background:linear-gradient(135deg,#1D4ED8,#1E40AF);border-radius:14px;padding:26px 32px;margin-bottom:20px}
.hdr h1{font-size:1.65rem;font-weight:700;color:#fff!important;margin:0 0 6px 0}
.hdr p{color:#BFDBFE!important;margin:0;font-size:.85rem;line-height:1.6}
.sec{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;
     color:#1D4ED8;padding-bottom:6px;border-bottom:2px solid #DBEAFE;margin:18px 0 10px}
.gradio-container label{color:#475569!important;font-size:.77rem!important;font-weight:600!important}
.gradio-container textarea,.gradio-container input[type=number]{
    background:#fff!important;border:1px solid #CBD5E1!important;
    color:#1E293B!important;border-radius:8px!important;font-size:.88rem!important}
.btn button{background:#1D4ED8!important;color:#fff!important;font-weight:700!important;
    font-size:1rem!important;border-radius:8px!important;border:none!important;
    padding:14px!important;width:100%!important;
    box-shadow:0 2px 12px rgba(29,78,216,.35)!important}
.btn button:hover{background:#1E40AF!important}
.warn textarea{background:#FFF7ED!important;border:1px solid #FED7AA!important;
    color:#92400E!important;font-weight:600!important}
.ftr{text-align:center;color:#94A3B8;font-size:.75rem;
    margin-top:24px;padding:16px;border-top:1px solid #E2E8F0}
"""


def build_ui():
    with gr.Blocks(title="Sistem Penilaian Luka Bakar") as demo:
        gr.HTML("""
        <div class="hdr">
          <h1>🏥 Sistem Penilaian Luka Bakar</h1>
          <p>Deteksi AI Otomatis (Gemini) &nbsp;|&nbsp; Lund-Browder Chart &nbsp;|&nbsp; Formula Parkland</p>
        </div>""")

        with gr.Row(equal_height=False):
            with gr.Column(scale=1, min_width=340):
                gr.HTML('<p class="sec">📷 Foto Luka Bakar</p>')
                img_in = gr.Image(type="filepath", label="Upload Foto Luka Bakar", height=260)

                gr.HTML('<p class="sec">👤 Data Pasien</p>')
                with gr.Row():
                    age_in = gr.Number(value=25, label="Usia (tahun)", minimum=0, maximum=120, precision=0)
                    wt_in = gr.Number(value=60, label="Berat Badan (kg)", minimum=1, maximum=300, precision=1)

                gr.HTML('<div style="height:10px"></div>')
                with gr.Row(elem_classes=["btn"]):
                    btn = gr.Button("🔍  Analisis Luka Bakar", variant="primary")

                gr.HTML("""
                <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-left:4px solid #1D4ED8;
                     border-radius:8px;padding:10px 14px;font-size:.79rem;color:#1E40AF;
                     line-height:1.8;margin-top:10px">
                  <b>Petunjuk:</b><br>
                  1. Upload foto luka bakar yang jelas<br>
                  2. Isi usia dan berat badan pasien<br>
                  3. Klik <em>Analisis Luka Bakar</em><br>
                  4. Tunggu 15–60 detik<br>
                  5. Jika gagal, klik sekali lagi
                </div>""")

            with gr.Column(scale=1, min_width=420):
                gr.HTML('<p class="sec">📊 Estimasi TBSA</p>')
                tbsa_out = gr.Textbox(label="Hasil Deteksi AI + TBSA (Lund-Browder)",
                                      lines=4, interactive=False)
                with gr.Row():
                    deg_out = gr.Textbox(label="Derajat Luka Bakar", lines=1, interactive=False)
                    sev_out = gr.Textbox(label="Klasifikasi Keparahan", lines=1, interactive=False)

                gr.HTML('<p class="sec">💧 Terapi Cairan — Formula Parkland</p>')
                fluid_out = gr.Textbox(label="Total Cairan 24 Jam", lines=3, interactive=False)
                sched_out = gr.Textbox(label="Jadwal Pemberian Cairan", lines=7, interactive=False)

                gr.HTML('<p class="sec">📝 Rekomendasi Klinis (RAG)</p>')
                rag_out = gr.Textbox(label="Panduan Manajemen Klinis", lines=12, interactive=False)
                refs_out = gr.Textbox(label="Referensi", lines=3, interactive=False)
                warn_out = gr.Textbox(label="⚠️ Peringatan Klinis",
                                      lines=3, interactive=False, elem_classes=["warn"])

        gr.HTML("""
        <div class="ftr">
          Sistem Penilaian Luka Bakar &nbsp;|&nbsp; Lund-Browder Chart &nbsp;|&nbsp;
          Formula Parkland (Baxter CR, 1974)<br>
          Alat bantu klinis — keputusan akhir tetap pada tenaga medis.
        </div>""")

        btn.click(
            fn=analyze,
            inputs=[img_in, age_in, wt_in],
            outputs=[tbsa_out, deg_out, sev_out,
                     fluid_out, sched_out, rag_out, refs_out, warn_out],
            show_progress=True,
        )

    return demo


if __name__ == "__main__":
    build_ui().launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        css=CSS,
    )
