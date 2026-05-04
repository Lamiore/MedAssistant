"""
orders.py
=========
Conditional initial-orders checklist generator for burn assessment.
Pure function: inputs in, list of order strings out. No I/O.
"""


def build_checklist(
    *,
    tbsa: float,
    age: int,
    weight_kg: float,
    mechanism: str,
    inhalation: bool,
    circumferential: bool,
) -> list[str]:
    """
    Return a list of clinician-facing order strings, ordered by priority.
    Each string is suitable for direct rendering in a checklist.
    """
    items: list[str] = []

    # Vascular access
    if tbsa >= 30.0:
        items.append(
            "IV access — 2× large-bore (16-18G) perifer + central line "
            "(TBSA ≥ 30%)"
        )
    else:
        items.append("IV access — 2× large-bore (16-18G) perifer")

    # Labs
    lab_extras: list[str] = []
    if mechanism == "Electrical":
        lab_extras.append("CK serial")
    lab_base = "CBC, BMP, ABG + carboxyHb, lactate, urinalisis"
    if lab_extras:
        items.append(f"Lab — {lab_base}, {', '.join(lab_extras)}")
    else:
        items.append(f"Lab — {lab_base}")

    # Imaging
    imaging_parts: list[str] = []
    if inhalation:
        imaging_parts.append("CXR (inhalation suspek)")
    if mechanism == "Electrical":
        imaging_parts.append("EKG 12-lead + monitoring kontinu")
    if imaging_parts:
        items.append("Imaging / EKG — " + " · ".join(imaging_parts))

    # Tetanus
    items.append("Tetanus — TT booster bila >5 thn / status tidak jelas")

    # Analgesia (morphine 0.05–0.1 mg/kg → range)
    low = round(0.05 * weight_kg, 1)
    high = round(0.10 * weight_kg, 1)
    items.append(
        f"Analgesia — Morfin IV {low:g}-{high:g} mg titrasi q5-10min "
        f"(0.05-0.1 mg/kg) · target NRS <4"
    )

    # Foley
    items.append("Foley catheter — monitor urine output 0.5-1 mL/kg/jam")

    # NGT for large burns (gastric ileus risk)
    if tbsa > 20.0:
        items.append("NGT — pasang (TBSA > 20%, risiko gastric ileus)")

    # NPO
    items.append("NPO — antisipasi anestesi/intubasi")

    # Inhalation-specific
    if inhalation:
        items.append(
            "⚠ Intubasi-ready — siapkan ETT, lakukan early intubation bila "
            "stridor / hoarseness / progressif"
        )

    # Chemical decontamination
    if mechanism == "Chemical":
        items.append(
            "Dekontaminasi — copot pakaian terkontaminasi, irigasi air mengalir "
            "≥ 20 menit (alkali ≥ 1 jam)"
        )

    # Circumferential
    if circumferential:
        items.append(
            "Escharotomy konsul — circumferential burn, monitor distal pulses "
            "& compartment pressure"
        )

    return items
