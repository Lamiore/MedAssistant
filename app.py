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
from html import escape

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

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
    age_i = max(0, age_i)

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
        return _empty_six(f"❌ Gagal membaca gambar: {escape(str(e))}")

    # ── Vision (Gemini) ──────────────────────────────────────────────────────
    ai = call_gemini_vision(image, age_i)
    if ai is None:
        return _empty_six(
            "⚠️ Semua model AI gagal menganalisis foto. "
            "Cek koneksi dan rate limit Gemini, lalu coba lagi dalam 1-2 menit."
        )

    tbsa = ai.get("tbsa_percent", 0.0) or 0.0
    burn_degree = ai.get("burn_degree") or "Unknown"

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

/* Header */
.hdr{background:linear-gradient(135deg,#1D4ED8,#1E40AF);border-radius:12px;
     padding:22px 28px;margin-bottom:14px}
.hdr h1{font-size:1.6rem;font-weight:700;color:#fff!important;margin:0 0 4px 0}
.hdr p{color:#BFDBFE!important;margin:0;font-size:.82rem;line-height:1.6}

/* Section labels */
.sec{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;
     color:#1D4ED8;padding-bottom:5px;border-bottom:2px solid #DBEAFE;margin:16px 0 10px}
.sec-label{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;
           color:#1D4ED8;margin-bottom:6px}

/* Inputs */
.gradio-container label{color:#475569!important;font-size:.78rem!important;font-weight:600!important}
.gradio-container textarea,.gradio-container input[type=number],
.gradio-container input[type=text],.gradio-container select{
    background:#fff!important;border:1px solid #CBD5E1!important;
    color:#1E293B!important;border-radius:6px!important;font-size:.88rem!important}

/* Submit button */
.btn button{background:#1D4ED8!important;color:#fff!important;font-weight:700!important;
    font-size:.95rem!important;border-radius:7px!important;border:none!important;
    padding:13px!important;width:100%!important;
    box-shadow:0 2px 12px rgba(29,78,216,.35)!important}
.btn button:hover{background:#1E40AF!important}

/* KPI banner */
.kpi-banner{background:#fff;border:1px solid #1D4ED8;border-left:5px solid #1D4ED8;
            border-radius:8px;padding:14px 18px;margin-bottom:10px}
.kpi-label{font-size:.68rem;color:#1D4ED8;text-transform:uppercase;font-weight:700;
           letter-spacing:1.5px;margin-bottom:8px}
.kpi-grid{display:grid;grid-template-columns:1.4fr 1fr 1.2fr 1fr 1.3fr;gap:14px}
.kpi-key{font-size:.68rem;color:#64748B;font-weight:600;letter-spacing:.5px;text-transform:uppercase}
.kpi-val{font-size:.95rem;font-weight:700;color:#1E293B;line-height:1.15;margin-top:2px}
.kpi-big{font-size:1.4rem!important}
.kpi-sub{font-size:.7rem;color:#64748B;margin-top:1px}

/* Tab sections */
.tab-section{margin-bottom:14px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:6px 14px;font-size:.82rem;line-height:1.6}
.muted{color:#64748B}
.kpi-hint{font-size:.74rem}

/* Cards */
.card-primary{background:#EFF6FF;border:1px solid #BFDBFE;border-left:4px solid #1D4ED8;
              border-radius:6px;padding:11px 14px}
.card-soft{background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px;padding:10px 12px}
.card-disp{border:1px solid;border-left:4px solid;border-radius:6px;padding:11px 14px}
.big-num{font-size:.95rem;font-weight:700;color:#1E293B;margin-top:3px}
.num-md{font-size:1rem;font-weight:700}
.reasons{margin:6px 0 0 18px;font-size:.78rem;color:#475569;line-height:1.6}

/* Confidence bar */
.conf-row{display:flex;align-items:center;gap:10px;font-size:.82rem}
.conf-bar{flex:1;background:#F1F5F9;height:9px;border-radius:5px;overflow:hidden}
.conf-fill{height:100%;border-radius:5px}

/* Red flag chips */
.flag-row{display:flex;flex-wrap:wrap;gap:5px}
.flag-chip{padding:4px 10px;border-radius:99px;font-size:.78rem;font-weight:600}
.flag-clear{font-weight:400!important}

/* Orders list */
.orders-list{font-size:.82rem;line-height:1.85}
.order-item{padding:1px 0}

/* Formula compare table */
.form-compare{width:100%;border-collapse:collapse;font-size:.8rem}
.form-compare thead{background:#F1F5F9}
.form-compare th{text-align:left;padding:6px 8px;border-bottom:2px solid #CBD5E1}
.form-compare td{padding:5px 8px;border-bottom:1px solid #E2E8F0}

/* Timeline */
.timeline{list-style:none;padding:0 0 0 18px;margin:0;border-left:2px solid #DBEAFE}
.tl-item{position:relative;padding-bottom:10px}
.tl-dot{position:absolute;left:-23px;top:2px;width:8px;height:8px;background:#fff;
        border:2px solid #1D4ED8;border-radius:50%}
.tl-dot-active{background:#1D4ED8;box-shadow:0 0 0 2px #1D4ED8}
.tl-active .tl-time{color:#1E40AF}
.tl-time{font-size:.82rem;font-weight:700;color:#475569}
.tl-body{font-size:.78rem;color:#475569;margin-top:2px}

/* RAG block */
.rag-block{background:#F8FAFC;border-radius:6px;padding:10px 12px;
           font-size:.82rem;line-height:1.7;color:#1E293B;white-space:pre-wrap}
.refs{margin:0 0 0 18px;font-size:.78rem;color:#475569;line-height:1.7}

/* Alerts */
.alert-warn{background:#FFF7ED;border:1px solid #FED7AA;border-radius:5px;
            padding:8px 11px;font-size:.78rem;color:#92400E;margin-top:6px}

/* Hint card */
.hint{background:#EFF6FF;border:1px solid #BFDBFE;border-left:4px solid #1D4ED8;
      border-radius:7px;padding:10px 13px;font-size:.78rem;color:#1E40AF;line-height:1.7;margin-top:10px}

/* Risk checkbox cards */
.risk-card label{background:#FFF7ED!important;border:1px solid #FED7AA!important;
                 padding:6px 8px!important;border-radius:5px!important;
                 color:#92400E!important;display:block!important;margin-bottom:5px!important}

/* Footer */
.ftr{text-align:center;color:#64748B;font-size:.74rem;margin-top:22px;
     padding:14px;border-top:1px solid #E2E8F0}
"""


def build_ui():
    with gr.Blocks(title="Sistem Penilaian Luka Bakar") as demo:
        gr.HTML("""
        <div class="hdr">
          <h1>🏥 Sistem Penilaian Luka Bakar</h1>
          <p>Clinical Decision Aid · Lund-Browder · Parkland · ABA Burn Center Criteria</p>
        </div>""")

        with gr.Row(equal_height=False):
            # ── Sidebar (left) ──────────────────────────────────────────────
            with gr.Column(scale=1, min_width=340):
                gr.HTML('<p class="sec">📷 Foto Luka Bakar</p>')
                img_in = gr.Image(type="filepath", label="Upload Foto", height=220)

                gr.HTML('<p class="sec">👤 Data Pasien</p>')
                with gr.Row():
                    age_in = gr.Number(value=25, label="Usia (th)",
                                       minimum=0, maximum=120, precision=0)
                    wt_in = gr.Number(value=60, label="Berat (kg)",
                                      minimum=1, maximum=300, precision=1)
                with gr.Row():
                    ht_in = gr.Number(value=None, label="Tinggi (cm) — opt",
                                      minimum=30, maximum=250, precision=1)
                    hrs_in = gr.Number(value=0, label="Jam sejak luka",
                                       minimum=0, maximum=72, precision=1)

                gr.HTML('<p class="sec">⚕️ Mekanisme &amp; Risiko</p>')
                mech_in = gr.Dropdown(
                    choices=["Thermal", "Electrical", "Chemical"],
                    value="Thermal", label="Mekanisme cedera",
                )
                with gr.Group(elem_classes=["risk-card"]):
                    inhal_in = gr.Checkbox(label="Suspek inhalation injury (face/neck burn, hoarse, soot)")
                    circ_in = gr.Checkbox(label="Circumferential burn (melilit ekstremitas / dada)")
                comorb_in = gr.CheckboxGroup(
                    choices=["DM", "CKD", "Jantung", "Hamil"],
                    value=[], label="Komorbid (opt)",
                )

                with gr.Row(elem_classes=["btn"]):
                    btn = gr.Button("🔍  Analisis Luka Bakar", variant="primary")

                gr.HTML("""
                <div class="hint">
                  <b>Petunjuk:</b><br>
                  1. Upload foto luka bakar yang jelas<br>
                  2. Isi data pasien &amp; mekanisme<br>
                  3. Klik <em>Analisis</em> · tunggu 15-60 detik<br>
                  4. Jika gagal, klik sekali lagi<br>
                  <br>
                  <em>Jam sejak luka</em> dipakai untuk menghitung catch-up rate Parkland bila pasien datang terlambat.
                </div>""")

            # ── Output area (right) ─────────────────────────────────────────
            with gr.Column(scale=2, min_width=520):
                banner_out = gr.HTML(value='<div class="kpi-banner"><div class="kpi-label">PATIENT BANNER · KPI</div><div class="muted kpi-hint">Hasil akan tampil setelah Analisis.</div></div>')

                with gr.Tabs():
                    with gr.Tab("📊 Ringkasan"):
                        summary_out = gr.HTML(value='<div class="muted kpi-hint">Belum ada hasil.</div>')
                    with gr.Tab("💧 Cairan"):
                        fluid_out = gr.HTML(value='<div class="muted kpi-hint">Belum ada hasil.</div>')
                    with gr.Tab("📋 Orders"):
                        orders_out = gr.HTML(value='<div class="muted kpi-hint">Belum ada hasil.</div>')
                    with gr.Tab("⏱ Monitoring"):
                        monitoring_out = gr.HTML(value='<div class="muted kpi-hint">Belum ada hasil.</div>')
                    with gr.Tab("📚 Edukasi & Refs"):
                        education_out = gr.HTML(value='<div class="muted kpi-hint">Belum ada hasil.</div>')

        gr.HTML("""
        <div class="ftr">
          Sistem Penilaian Luka Bakar · Lund-Browder · Parkland (Baxter, 1974) · ABA Criteria<br>
          Alat bantu klinis — keputusan akhir tetap pada tenaga medis.
        </div>""")

        btn.click(
            fn=analyze,
            inputs=[img_in, age_in, wt_in, ht_in, hrs_in,
                    mech_in, inhal_in, circ_in, comorb_in],
            outputs=[banner_out, summary_out, fluid_out,
                     orders_out, monitoring_out, education_out],
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
