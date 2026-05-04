"""
renderers.py
============
Pure HTML rendering functions. Each takes a results dict and returns an
HTML string. No Gradio imports, no I/O.

The results dict shape is the contract between analyze() and the renderers.
See tests/test_renderers.py::_sample_results for the canonical example.
"""

from html import escape


# ── helpers ──────────────────────────────────────────────────────────────────

def _fmt_int(n) -> str:
    if n is None:
        return "—"
    try:
        return f"{int(round(float(n))):,}"
    except (TypeError, ValueError):
        return "—"


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
    age_cat = "Pediatric" if isinstance(age, int) and age < 14 else (
        "Geriatric" if isinstance(age, int) and age >= 65 else "Adult"
    )

    tbsa = ai.get("tbsa", 0.0)
    degree = escape(str(ai.get("burn_degree", "—")))
    severity = r.get("severity", "—")
    sev_icon = _severity_icon(severity)
    disposition = r.get("disposition", "—")
    disp_color = _disposition_color(disposition)
    fluid_total = fluid.get("total_24h_ml")

    return f"""
    <div class="kpi-banner">
      <div class="kpi-label">PATIENT BANNER · KPI</div>
      <div class="kpi-grid">
        <div class="kpi-tile">
          <div class="kpi-key">PASIEN</div>
          <div class="kpi-val">{age}y · {weight}kg · {bsa_str}</div>
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
          <div class="kpi-sub">{("ABA criteria met" if disposition != "Outpatient / Klinik Rawat Jalan" else "—")}</div>
        </div>
      </div>
    </div>
    """


def _severity_subtitle(tbsa: float) -> str:
    if tbsa > 40: return "> 40% TBSA"
    if tbsa > 20: return "> 20% TBSA"
    if tbsa >= 10: return "10–20% TBSA"
    return "< 10% TBSA"


# ── summary tab ──────────────────────────────────────────────────────────────

def summary_html(r: dict) -> str:
    ai = r.get("ai", {})
    flags = r.get("red_flags", [])

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
      <div class="muted small">Konfirmasi manual dengan Lund-Browder chart fisik tetap dianjurkan.</div>
    </div>

    <div class="tab-section">
      <div class="sec-label">🚩 RED FLAGS</div>
      <div class="flag-row">{flag_html}</div>
    </div>
    """
