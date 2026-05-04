"""
triage.py
=========
ABA Burn Center Referral Criteria → disposition (deterministic, rule-based).
Red-flag aggregator for the Ringkasan tab.

References:
- American Burn Association Burn Center Referral Criteria (2022)
"""

from typing import Iterable


def classify(
    *,
    tbsa: float,
    age: int,
    mechanism: str,
    inhalation: bool,
    circumferential: bool,
    comorbid: Iterable[str],
    burn_degree: str,
) -> tuple[str, list[str]]:
    """
    Return (disposition, reasons[]).

    Disposition tiers (most-acute first):
        "Burn ICU / Burn Center"        – TBSA > 20%, OR inhalation,
                                          OR any of the above on top of any
                                          burn-center criteria.
        "Burn Center (Refer)"           – any ABA referral criterion met.
        "Bangsal Bedah / Burn Unit"     – TBSA 5–10% partial thickness.
        "Outpatient / Klinik Rawat Jalan" – TBSA <5%, no other criteria.

    `reasons` is a human-readable list of which criteria fired.
    """
    reasons: list[str] = []

    is_third_degree = "Third degree" in (burn_degree or "")
    is_pediatric = age < 5
    is_geriatric = age >= 65
    has_comorbid = bool(list(comorbid))

    # ABA Burn Center Referral Criteria
    if tbsa >= 10.0:
        reasons.append(f"TBSA ≥ 10% partial-thickness ({tbsa:.1f}%)")
    if is_third_degree:
        reasons.append("Any 3rd-degree burn")
    if mechanism == "Electrical":
        reasons.append("Electrical burn (rhabdomyolysis/cardiac risk)")
    if mechanism == "Chemical":
        reasons.append("Chemical burn (decontamination required)")
    if inhalation:
        reasons.append("Inhalation injury suspected")
    if circumferential:
        reasons.append("Circumferential burn (escharotomy risk)")
    if is_pediatric and tbsa >= 5.0:
        reasons.append(f"Pediatric (age {age}) with TBSA ≥ 5%")
    if is_geriatric and has_comorbid:
        reasons.append(f"Comorbid + age ≥65 ({', '.join(comorbid)})")

    # Escalation to ICU
    icu_reasons: list[str] = []
    if tbsa > 20.0:
        icu_reasons.append(f"TBSA > 20% ({tbsa:.1f}%)")
    if inhalation:
        icu_reasons.append("Inhalation injury suspected")

    if icu_reasons:
        # ICU disposition includes ICU-level reasons first, then any other
        # burn-center criteria.
        all_reasons = icu_reasons + [r for r in reasons if r not in icu_reasons]
        return "Burn ICU / Burn Center", all_reasons

    if reasons:
        return "Burn Center (Refer)", reasons

    if tbsa >= 5.0:
        return "Bangsal Bedah / Burn Unit", [f"TBSA {tbsa:.1f}% (5–10% range)"]

    return "Outpatient / Klinik Rawat Jalan", []


def red_flags(
    *,
    tbsa: float,
    inhalation: bool,
    circumferential: bool,
    comorbid: Iterable[str],
) -> list[tuple[str, bool]]:
    """
    Return a fixed list of (label, active) tuples for the Ringkasan red-flag chips.

    Order is stable so the UI can render "active" red and "clear" gray reliably.
    """
    return [
        ("Inhalation injury", bool(inhalation)),
        ("Circumferential burn", bool(circumferential)),
        ("Komorbid", bool(list(comorbid))),
        ("TBSA > 20%", tbsa > 20.0),
    ]
