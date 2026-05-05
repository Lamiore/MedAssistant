"""
renderers.py
============
Pure HTML rendering functions. Each takes a results dict and returns an
HTML string. No Gradio imports, no I/O.

The results dict shape is the contract between analyze() and the renderers.
See tests/test_renderers.py::_sample_results for the canonical example.
"""

import math
from html import escape


# ── helpers ──────────────────────────────────────────────────────────────────

def _fmt_int(n) -> str:
    if n is None:
        return "—"
    try:
        f = float(n)
        if not math.isfinite(f):
            return "—"
        return f"{int(round(f)):,}"
    except (TypeError, ValueError):
        return "—"


# Used by fluid_html and orders_html (Tasks 5/6).
def _fmt_pct(n, decimals=1) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n):.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def _disposition_color(disposition: str) -> str:
    d = (disposition or "").lower()
    if "icu" in d:
        return "#DC2626"  # red
    if "refer" in d or "burn center" in d:
        return "#EA580C"  # orange
    if "bangsal" in d or "ward" in d:
        return "#2563EB"  # blue
    return "#16A34A"      # green (outpatient)


def _severity_icon(severity: str) -> str:
    s = (severity or "").lower()
    if "critical" in s:
        return "🚨"
    if "major" in s or "severe" in s:
        return "🔴"
    if "moderate" in s:
        return "🟡"
    return "🟢"


def _severity_subtitle(tbsa: float) -> str:
    if tbsa > 40: return "> 40% TBSA"
    if tbsa > 20: return "> 20% TBSA"
    if tbsa >= 10: return "10–20% TBSA"
    return "< 10% TBSA"


# ── banner ───────────────────────────────────────────────────────────────────

def banner_html(r: dict) -> str:
    p = r.get("patient", {})
    ai = r.get("ai", {})
    fluid = r.get("fluid", {})

    age = p.get("age", "—")
    weight = p.get("weight", "—")
    bsa = p.get("bsa_m2")
    bsa_str = f"BSA {bsa:.2f}m²" if isinstance(bsa, (int, float)) else "BSA —"
    mech = escape(str(p.get("mechanism", "—")))
    try:
        age_n = int(age)
    except (TypeError, ValueError):
        age_n = None
    age_cat = ("Pediatric" if age_n is not None and age_n < 14
               else "Geriatric" if age_n is not None and age_n >= 65
               else "Adult")

    tbsa = float(ai.get("tbsa") or 0.0)
    degree = escape(str(ai.get("burn_degree", "—")))
    severity = r.get("severity") or "—"
    sev_icon = _severity_icon(severity)
    disposition = r.get("disposition") or "—"
    disp_color = _disposition_color(disposition)
    fluid_total = fluid.get("total_24h_ml")

    return f"""
    <div class="kpi-banner">
      <div class="kpi-label">PATIENT BANNER · KPI</div>
      <div class="kpi-grid">
        <div class="kpi-tile">
          <div class="kpi-key">PASIEN</div>
          <div class="kpi-val">{escape(str(age))}y · {escape(str(weight))}kg · {bsa_str}</div>
          <div class="kpi-sub">{age_cat} · {mech}</div>
        </div>
        <div class="kpi-tile">
          <div class="kpi-key">TBSA</div>
          <div class="kpi-val kpi-big" style="color:#1E40AF">{tbsa:.1f}<span style="font-size:.6em;color:#64748B">%</span></div>
          <div class="kpi-sub">{degree}</div>
        </div>
        <div class="kpi-tile">
          <div class="kpi-key">SEVERITY</div>
          <div class="kpi-val">{sev_icon} {escape(severity)}</div>
          <div class="kpi-sub">{_severity_subtitle(tbsa)}</div>
        </div>
        <div class="kpi-tile">
          <div class="kpi-key">FLUID 24h</div>
          <div class="kpi-val">{_fmt_int(fluid_total)} mL</div>
          <div class="kpi-sub">RL · Parkland</div>
        </div>
        <div class="kpi-tile">
          <div class="kpi-key">DISPOSITION</div>
          <div class="kpi-val" style="color:{disp_color}">→ {escape(disposition)}</div>
          <div class="kpi-sub">{("ABA criteria met" if "outpatient" not in disposition.lower() else "—")}</div>
        </div>
      </div>
    </div>
    """


# ── summary tab ──────────────────────────────────────────────────────────────

def summary_html(r: dict) -> str:
    ai = r.get("ai", {})
    flags = r.get("red_flags") or []

    degree = escape(str(ai.get("burn_degree", "—")))
    areas = ", ".join(escape(a) for a in ai.get("areas", [])) or "—"
    desc = escape(str(ai.get("description", "—")))
    conf = str(ai.get("confidence", "medium")).lower()

    conf_pct = {"high": 85, "medium": 60, "low": 30}.get(conf, 50)
    conf_label = conf.upper()
    conf_color = {"high": "#0F766E", "medium": "#A16207", "low": "#B91C1C"}.get(
        conf, "#475569"
    )

    flag_chips = []
    for label, active in flags:
        if active:
            flag_chips.append(
                f'<span class="flag-chip flag-active" style="background:#FEE2E2;color:#991B1B">⚠ {escape(label)}</span>'
            )
        else:
            flag_chips.append(
                f'<span class="flag-chip flag-clear" style="background:#F1F5F9;color:#64748B">○ {escape(label)} — clear</span>'
            )
    flag_html = "".join(flag_chips) or '<span class="kpi-sub">—</span>'

    return f"""
    <div class="tab-section">
      <div class="sec-label">📷 AI DETECTION</div>
      <div class="grid-2">
        <div><span class="muted">Derajat:</span> <b>{degree}</b></div>
        <div><span class="muted">Areas:</span> {areas}</div>
        <div style="grid-column:1/-1"><span class="muted">Karakteristik:</span> {desc}</div>
      </div>
    </div>

    <div class="tab-section">
      <div class="sec-label">🤖 AI CONFIDENCE</div>
      <div class="conf-row">
        <div class="conf-bar"><div class="conf-fill" style="width:{conf_pct}%;background:linear-gradient(to right,#FBBF24,#34D399)"></div></div>
        <div style="font-weight:700;color:{conf_color}">{conf_label} ({conf_pct}%)</div>
      </div>
      <div class="muted kpi-hint">Konfirmasi manual dengan Lund-Browder chart fisik tetap dianjurkan.</div>
    </div>

    <div class="tab-section">
      <div class="sec-label">🚩 RED FLAGS</div>
      <div class="flag-row">{flag_html}</div>
    </div>
    """


# ── fluid tab ────────────────────────────────────────────────────────────────

def fluid_html(r: dict) -> str:
    fluid = r.get("fluid", {})
    brooke = r.get("brooke", {})
    p = r.get("patient", {})
    weight = p.get("weight") or 0

    total = fluid.get("total_24h_ml") or 0
    first8 = fluid.get("first_8h_ml") or 0
    rest = fluid.get("next_16h_ml") or 0
    rate1 = fluid.get("rate_first_8h_mlph") or 0
    rate2 = fluid.get("rate_next_16h_mlph") or 0
    lag = fluid.get("lag_status") or "on_time"
    catchup = fluid.get("catchup_rate_mlph")  # genuinely Optional, kept as-is
    rem = fluid.get("hours_remaining_first_8h") or 8
    hours_since = r.get("hours_since") or 0

    # Catch-up alert
    if lag == "catching_up" and catchup is not None:
        catchup_alert = f"""
        <div class="alert-warn">
          ⏱ <b>Tertinggal {hours_since:g} jam.</b> 8-jam pertama tinggal {rem:g} jam —
          naikkan rate ke <b>~{catchup:g} mL/jam</b> sampai catch-up.
        </div>
        """
    elif lag == "first_8h_passed":
        catchup_alert = """
        <div class="alert-warn">
          ⚠ <b>8-jam pertama sudah terlewat</b> — titrasi cairan sesuai urine
          output aktual (target 0.5–1 mL/kg/jam).
        </div>
        """
    else:
        catchup_alert = ""

    brooke_total = brooke.get("total_24h_ml", 0)
    weight_target = (
        f"{0.5 * weight:.0f}–{1.0 * weight:.0f} mL/jam"
        if weight else "—"
    )

    return f"""
    <div class="tab-section">
      <div class="card-primary">
        <div class="sec-label" style="color:#1E40AF">PARKLAND (Default)</div>
        <div class="big-num">{_fmt_int(total)} mL · Ringer Laktat · 24 jam</div>
        <div class="muted kpi-hint">Rumus: 4 mL × {weight:g} kg × TBSA% · Target urine {weight_target}</div>
      </div>
    </div>

    <div class="tab-section">
      <div class="sec-label">📅 JADWAL PEMBERIAN</div>
      <div class="grid-2">
        <div class="card-soft">
          <div class="muted kpi-hint">8 JAM PERTAMA</div>
          <div class="num-md">{_fmt_int(first8)} mL</div>
          <div class="muted kpi-hint">@ {rate1:.1f} mL/jam · dari saat kejadian</div>
        </div>
        <div class="card-soft">
          <div class="muted kpi-hint">16 JAM BERIKUTNYA</div>
          <div class="num-md">{_fmt_int(rest)} mL</div>
          <div class="muted kpi-hint">@ {rate2:.1f} mL/jam</div>
        </div>
      </div>
      {catchup_alert}
    </div>

    <div class="tab-section">
      <div class="sec-label">📊 PERBANDINGAN FORMULA</div>
      <table class="form-compare">
        <thead><tr><th>Formula</th><th style="text-align:right">Total 24h</th><th>Cairan</th><th>Catatan</th></tr></thead>
        <tbody>
          <tr><td><b>Parkland</b> ⭐</td><td style="text-align:right;font-weight:700">{_fmt_int(total)} mL</td><td>RL</td><td class="muted">4 mL/kg/%</td></tr>
          <tr><td>Modified Brooke</td><td style="text-align:right">{_fmt_int(brooke_total)} mL</td><td>RL</td><td class="muted">2 mL/kg/%</td></tr>
          <tr><td>Galveston (peds)</td><td style="text-align:right" class="muted">— N/A —</td><td class="muted">—</td><td class="muted">untuk usia &lt; 14</td></tr>
        </tbody>
      </table>
    </div>
    """


# ── orders tab ───────────────────────────────────────────────────────────────

def orders_html(r: dict) -> str:
    disposition = r.get("disposition") or "—"
    reasons = r.get("disposition_reasons") or []
    orders = r.get("orders") or []
    disp_color = _disposition_color(disposition)

    disp_bg = {
        "#DC2626": "#FEE2E2", "#EA580C": "#FFEDD5",
        "#2563EB": "#DBEAFE", "#16A34A": "#DCFCE7",
    }.get(disp_color, "#F1F5F9")

    reasons_html = "".join(
        f"<li>{escape(reason)}</li>" for reason in reasons
    ) or "<li class='muted'>—</li>"

    orders_items = "".join(
        f"<div class='order-item'>{'⚠' if o.startswith('⚠') else '☑'} {escape(o.removeprefix('⚠ '))}</div>"
        for o in orders
    ) or "<div class='order-item muted'>—</div>"

    return f"""
    <div class="tab-section">
      <div class="card-disp" style="background:{disp_bg};border-left-color:{disp_color}">
        <div class="sec-label" style="color:{disp_color}">DISPOSITION</div>
        <div class="big-num" style="color:{disp_color}">→ {escape(disposition)}</div>
        <ul class="reasons">{reasons_html}</ul>
      </div>
    </div>

    <div class="tab-section">
      <div class="sec-label">📋 INITIAL ORDERS CHECKLIST</div>
      <div class="orders-list">
        {orders_items}
      </div>
    </div>

    <div class="tab-section">
      <div class="sec-label">💊 PAIN & WOUND CARE</div>
      <div class="muted kpi-hint">
        <b>Analgesia:</b> Morfin titrasi sesuai NRS · target NRS &lt; 4 ·
        re-evaluasi q5-10min<br>
        <b>Wound:</b> Silver sulfadiazine 1% topical untuk derajat 2 ·
        hydrogel/non-adherent untuk superficial · ganti dressing q24h
      </div>
    </div>
    """


# ── monitoring tab ───────────────────────────────────────────────────────────

def monitoring_html(r: dict) -> str:
    fluid = r.get("fluid") or {}
    rate1 = fluid.get("rate_first_8h_mlph") or 0
    rate2 = fluid.get("rate_next_16h_mlph") or 0
    warning = r.get("warning") or ""

    warning_html = (
        f'<div class="alert-warn">⚠ <b>Warning klinis:</b> {escape(warning)}</div>'
        if warning else ""
    )

    return f"""
    <div class="tab-section">
      <div class="sec-label">📅 24h MONITORING TIMELINE</div>
      <ul class="timeline">
        <li class="tl-item tl-active">
          <div class="tl-dot tl-dot-active"></div>
          <div class="tl-time">0–8 JAM</div>
          <div class="tl-body">Rate {rate1:.0f} mL/jam · cek urine /1jam · GCS · vitals q15min</div>
        </li>
        <li class="tl-item">
          <div class="tl-dot"></div>
          <div class="tl-time">8–16 JAM</div>
          <div class="tl-body">Rate {rate2:.0f} mL/jam · titrasi sesuai UO 0.5-1 mL/kg/jam</div>
        </li>
        <li class="tl-item">
          <div class="tl-dot"></div>
          <div class="tl-time">16–24 JAM</div>
          <div class="tl-body">Recheck TBSA manual · ABG ulang · plan eskar/graft · gizi enteral early</div>
        </li>
      </ul>
      {warning_html}
    </div>
    """


# ── education tab ────────────────────────────────────────────────────────────

_FALLBACK_REFS = [
    "ABA Guidelines on Management of Acute Burns (2022)",
    "Parkland Formula — Baxter CR, 1974",
    "Lund-Browder Chart (age-adjusted)",
    "ATLS Burn Module 10ed",
]


def education_html(r: dict) -> str:
    explanation = r.get("rag_explanation") or (
        "(Penjelasan RAG tidak tersedia — referensi statis di bawah ini.)"
    )
    refs = r.get("references") or _FALLBACK_REFS

    refs_html = "".join(f"<li>{escape(ref)}</li>" for ref in refs)

    return f"""
    <div class="tab-section">
      <div class="sec-label">📝 PANDUAN MANAJEMEN (RAG)</div>
      <div class="rag-block">{escape(explanation)}</div>
    </div>

    <div class="tab-section">
      <div class="sec-label">📖 REFERENSI</div>
      <ul class="refs">{refs_html}</ul>
    </div>
    """
