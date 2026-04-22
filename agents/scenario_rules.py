"""
Deterministic rules for international-student finance scenarios (Agent 5).
Used before / alongside model guidance — cautious heuristics only, not legal advice.
"""

from __future__ import annotations

import copy
import re
from typing import Any


def _uniq(seq: list) -> list:
    seen: set = set()
    out = []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def apply_scenario_rules(scenario: dict[str, Any], user_query: str = "") -> dict[str, Any]:
    """
    Rule sets A–F: enrich scenario + rules_hints for guidance.
    Does not remove model-extracted fields; overlays conservative defaults.
    """
    out = copy.deepcopy(scenario) if scenario else {}
    q = (user_query or "").lower()

    out.setdefault("visa_status", "unknown")
    out.setdefault("student_status", "unknown")
    out.setdefault("income_types", [])
    out.setdefault("residency_hint", "unknown")
    out.setdefault("years_in_us", "unknown")
    out.setdefault("has_ssn", None)
    out.setdefault("needs_itin", None)
    out.setdefault("state", "unknown")
    out.setdefault("risk_flags", [])
    out.setdefault("missing_info", [])

    if not isinstance(out["income_types"], list):
        out["income_types"] = []
    if not isinstance(out["risk_flags"], list):
        out["risk_flags"] = []
    if not isinstance(out["missing_info"], list):
        out["missing_info"] = []

    # --- Rule set A: F1 / OPT / CPT framing ---
    mentions_opt = bool(re.search(r"\bopt\b", q)) or str(out.get("visa_status", "")).upper() == "OPT"
    mentions_cpt = bool(re.search(r"\bcpt\b", q)) or str(out.get("visa_status", "")).upper() == "CPT"
    mentions_f1 = bool(re.search(r"f[\s-]?1\b", q, re.I))
    mentions_j1 = bool(re.search(r"j[\s-]?1\b", q, re.I))

    if mentions_cpt:
        out["visa_status"] = "CPT"
        out["student_status"] = "on_cpt"
    elif mentions_opt:
        out["visa_status"] = "OPT"
        out["student_status"] = "on_opt"
    elif mentions_f1 and not mentions_opt and not mentions_cpt:
        out["visa_status"] = "F1"
    elif mentions_j1 and not mentions_opt and not mentions_cpt:
        out["visa_status"] = "J1"

    # --- Rule set B: SSN / ITIN ---
    no_ssn_phrase = bool(
        re.search(
            r"(no|without|don'?t have|do not have|haven'?t got)\s*(an?\s*)?(ssn|social security)",
            q,
            re.I,
        )
    )
    if no_ssn_phrase or re.search(r"\bno\s+ssn\b", q, re.I):
        out["has_ssn"] = False

    income_lower = " ".join(out["income_types"]).lower() + " " + q
    taxable_signal = bool(
        re.search(r"w[\s-]?2|1099|wages?|salary|stipend|paid internship|employment income", income_lower, re.I)
    )
    if out.get("has_ssn") is False and taxable_signal:
        out["needs_itin"] = True

    # --- Rule set C & D: tax heuristics + FICA (passed to guidance, not definitive) ---
    visa_bucket = str(out.get("visa_status", "unknown")).upper()
    non_res_hint = str(out.get("residency_hint", "")).lower() in ("nonresident", "non-resident", "nr", "unknown")

    rules_hints: dict[str, Any] = {
        "form_8843_possible": visa_bucket in ("F1", "J1", "OPT", "CPT") or mentions_f1 or mentions_j1 or mentions_opt or mentions_cpt,
        "form_1040_nr_review": bool(re.search(r"w[\s-]?2", q, re.I) or "w-2" in income_lower),
        "scholarship_portion_watchout": bool(re.search(r"scholarship|fellowship|grant", q, re.I)),
        "1099_complexity_watchout": bool(re.search(r"1099", q, re.I)),
        "fica_review_suggested": visa_bucket in ("F1", "J1", "OPT", "CPT") or mentions_f1 or mentions_j1 or mentions_opt or mentions_cpt,
        "nonresident_tax_context": non_res_hint or visa_bucket in ("F1", "J1", "OPT", "CPT"),
    }

    if rules_hints["scholarship_portion_watchout"] and "Scholarship taxation (portion may be taxable)" not in out["risk_flags"]:
        out["risk_flags"].append("Scholarship taxation (portion may be taxable; rules vary)")

    if rules_hints["1099_complexity_watchout"]:
        out["risk_flags"].append(
            "1099 income often raises classification, work authorization, and tax complexity — verify carefully"
        )

    if rules_hints["fica_review_suggested"]:
        out["risk_flags"].append(
            "FICA (Social Security/Medicare) exemptions sometimes apply for eligible students — verify with payroll/IRS guidance; not definitive here"
        )

    # --- Rule set E: work authorization ---
    work_q = bool(
        re.search(
            r"can i work|work off[\s-]?campus|off[\s-]?campus|internship|gig|freelanc|uber|1099 contractor",
            q,
            re.I,
        )
    )
    if work_q:
        if "work_authorization_question" not in out["risk_flags"]:
            out["risk_flags"].append("work_authorization_question")
        for line in (
            "Is the role on-campus, CPT-authorized, OPT-authorized, or otherwise permitted under your visa category?",
            "Is employment direct W-2 or independent contractor / 1099?",
        ):
            if line not in out["missing_info"]:
                out["missing_info"].append(line)

    # --- Rule set F: uncertainty ---
    if out.get("years_in_us") in (None, "unknown", ""):
        if "Years in the U.S. (for residency tests)" not in out["missing_info"]:
            out["missing_info"].append("Years in the U.S. (for residency tests)")
    if out.get("visa_status") in ("unknown", ""):
        if "Specific visa subtype and I-20/DS-2019 details" not in out["missing_info"]:
            out["missing_info"].append("Specific visa subtype and I-20/DS-2019 details")
    if not out["income_types"] and not re.search(r"income|w[\s-]?2|1099|scholarship|stipend", q, re.I):
        if "Income types and amounts (if any)" not in out["missing_info"]:
            out["missing_info"].append("Income types and amounts (if any)")

    out["rules_hints"] = rules_hints
    out["risk_flags"] = _uniq(out["risk_flags"])
    out["missing_info"] = _uniq(out["missing_info"])
    return out
