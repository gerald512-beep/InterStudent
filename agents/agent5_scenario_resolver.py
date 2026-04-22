"""
Agent 5: Scenario Resolver — informational finance guidance for international students.
Not a general chatbot; two-stage extraction + grounded guidance with deterministic rules.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai.errors import ClientError

from agents.scenario_rules import apply_scenario_rules

load_dotenv()

_client = genai.Client(
    vertexai=True,
    project=os.environ.get("GOOGLE_CLOUD_PROJECT", "interstudent-nyc-2026"),
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

GENERATION_MODEL = "gemini-2.5-flash"

DISCLAIMER_TEXT = "Informational only; not legal, tax, or immigration advice."

MAX_CONTEXT_CHARS = 6000
MAX_SOURCES = 5


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _safe_generate(prompt: str, retries: int = 2) -> str:
    for attempt in range(retries):
        try:
            response = _client.models.generate_content(
                model=GENERATION_MODEL,
                contents=prompt,
            )
            return response.text or ""
        except ClientError as e:
            if "429" in str(e) and attempt < retries - 1:
                time.sleep(20 * (attempt + 1))
            else:
                return ""
        except Exception:
            return ""
    return ""


# ---------------------------------------------------------------------------
# Regex / heuristic extraction (fallback)
# ---------------------------------------------------------------------------

def fallback_extract_scenario(user_query: str) -> dict[str, Any]:
    q = (user_query or "").strip()
    low = q.lower()

    visa_status = "unknown"
    student_status = "unknown"
    if re.search(r"\bcpt\b", low):
        visa_status, student_status = "CPT", "on_cpt"
    elif re.search(r"\bopt\b", low):
        visa_status, student_status = "OPT", "on_opt"
    elif re.search(r"f[\s-]?1\b", low):
        visa_status = "F1"
    elif re.search(r"j[\s-]?1\b", low):
        visa_status = "J1"

    income_types: list[str] = []
    if re.search(r"w[\s-]?2|w2\b", low, re.I):
        income_types.append("W-2 wages")
    if re.search(r"1099", low):
        income_types.append("1099 / independent contractor")
    if re.search(r"scholarship|fellowship|grant", low, re.I):
        income_types.append("scholarship or fellowship")
    if re.search(r"on[\s-]?campus|assistantship|stipend", low, re.I):
        income_types.append("campus employment / stipend")

    has_ssn: bool | None = None
    if re.search(
        r"(no|without|don'?t have|do not have)\s*(an?\s*)?(ssn|social security)",
        low,
        re.I,
    ) or re.search(r"\bno\s+ssn\b", low, re.I):
        has_ssn = False
    elif re.search(r"\b(ssn|social security number)\b", low, re.I) and not re.search(
        r"no\s+ssn|don'?t have.*ssn", low, re.I
    ):
        has_ssn = True

    needs_itin: bool | None = None
    if re.search(r"\bitin\b", low, re.I):
        needs_itin = True

    years_in_us: str | int | float = "unknown"
    ym = re.search(
        r"(\d+)\s*(?:years?|yrs?)\s*(?:in\s*)?(?:the\s*)?(?:u\.s\.|us|united states)",
        low,
        re.I,
    )
    if ym:
        years_in_us = ym.group(1)

    residency_hint = "unknown"
    if re.search(r"non[\s-]?resident|nonresident|nr\b", low, re.I):
        residency_hint = "nonresident"
    elif re.search(r"resident alien|resident for tax", low, re.I):
        residency_hint = "resident"

    state = "unknown"
    if re.search(r"\bnyc\b|new york city|manhattan|brooklyn|queens", low, re.I):
        state = "NY (NYC area)"
    elif re.search(r"\bny\b|new york\b", low, re.I):
        state = "NY"

    risk_flags: list[str] = []
    missing_info: list[str] = []

    return {
        "visa_status": visa_status,
        "student_status": student_status,
        "income_types": income_types,
        "residency_hint": residency_hint,
        "years_in_us": years_in_us,
        "has_ssn": has_ssn,
        "needs_itin": needs_itin,
        "state": state,
        "risk_flags": risk_flags,
        "missing_info": missing_info,
    }


def _merge_scenario(model_s: dict[str, Any], fallback_s: dict[str, Any]) -> dict[str, Any]:
    """Prefer model fields when present and not 'unknown'; fill gaps from fallback."""
    out = dict(fallback_s)
    if not model_s:
        return out
    unk = {"unknown", "", None}

    def pick(key: str):
        mv = model_s.get(key)
        fv = fallback_s.get(key)
        if mv is None or mv == "unknown" or mv == []:
            return fv
        return mv

    for key in (
        "visa_status",
        "student_status",
        "residency_hint",
        "years_in_us",
        "state",
    ):
        val = model_s.get(key)
        if val not in unk and val is not None:
            out[key] = val

    if model_s.get("income_types"):
        merged = list(model_s["income_types"])
        for x in fallback_s.get("income_types") or []:
            if x not in merged:
                merged.append(x)
        out["income_types"] = merged
    if model_s.get("has_ssn") is not None:
        out["has_ssn"] = model_s["has_ssn"]
    if model_s.get("needs_itin") is not None:
        out["needs_itin"] = model_s["needs_itin"]
    if model_s.get("risk_flags"):
        out["risk_flags"] = list(
            dict.fromkeys((fallback_s.get("risk_flags") or []) + list(model_s["risk_flags"]))
        )
    if model_s.get("missing_info"):
        out["missing_info"] = list(
            dict.fromkeys((fallback_s.get("missing_info") or []) + list(model_s["missing_info"]))
        )
    return out


# ---------------------------------------------------------------------------
# Context from pipeline
# ---------------------------------------------------------------------------

def extract_agent5_context(
    retrieval_pack: dict | None,
    content_draft: dict | None,
    user_profile: dict | None = None,
) -> dict[str, Any]:
    rp = retrieval_pack or {}
    cd = content_draft or {}
    up = user_profile or {}

    topic = rp.get("query_topic") or cd.get("topic") or ""
    topic_angle = ""
    tr = cd.get("trend") if isinstance(cd.get("trend"), dict) else {}
    topic_angle = tr.get("topic_angle", "") or cd.get("topic", "")

    results = rp.get("results") or []
    sources: list[dict[str, str]] = []
    chunk: list[str] = []
    for r in results[:MAX_SOURCES]:
        url = (r.get("source_url") or "").strip()
        if not url:
            continue
        title = (r.get("title") or "Source")[:200]
        sources.append({"title": title, "url": url})
        snippet = (r.get("content_chunk") or "")[:400]
        chunk.append(f"- [{title}]({url}): {snippet}")

    grounding = "\n".join(chunk)[:MAX_CONTEXT_CHARS]

    persona_bits = {}
    if up:
        persona_bits = {
            "audience_segment": up.get("audience_segment"),
            "tone_preference": up.get("tone_preference"),
            "city_focus": up.get("city_focus"),
            "school_type": up.get("school_type"),
            "content_goal": up.get("content_goal"),
        }

    return {
        "pipeline_topic": topic,
        "topic_angle": topic_angle,
        "platform": cd.get("platform", "unknown"),
        "sources": sources,
        "grounding_snippets": grounding,
        "user_profile": {k: v for k, v in persona_bits.items() if v},
    }


# ---------------------------------------------------------------------------
# Model prompts
# ---------------------------------------------------------------------------

def _extract_prompt(user_query: str) -> str:
    return f"""You extract structured scenario fields from a short user message about international student finance or immigration-adjacent logistics in the U.S.

User message:
\"\"\"{user_query}\"\"\"

Return ONLY a JSON object with these keys (use string "unknown" or empty list [] when unsure; do not invent facts):
- visa_status: string (e.g. F1, J1, OPT, CPT, unknown)
- student_status: string (e.g. on_opt, on_cpt, enrolled, unknown)
- income_types: array of strings (e.g. W-2 wages, scholarship, 1099)
- residency_hint: string (nonresident, resident, unknown)
- years_in_us: string or number or "unknown"
- has_ssn: boolean or null if unknown
- needs_itin: boolean or null if unknown
- state: U.S. state or region or "unknown"
- risk_flags: array of short strings
- missing_info: array of short strings describing what is missing to give precise guidance

Rules:
- If the user did not mention something, use "unknown" or null — do not guess numbers or employers.
- Output valid JSON only, no markdown."""


def _guidance_prompt(normalized: dict[str, Any], context: dict[str, Any]) -> str:
    src_lines = ""
    for s in context.get("sources") or []:
        src_lines += f"- {s.get('title')}: {s.get('url')}\n"

    return f"""You are an informational assistant for international students navigating U.S. finance and related topics.

You MUST:
- Be empathetic, plain English, concise.
- Use cautious language: "likely", "may", "often", "depends" — never guarantee immigration or tax outcomes.
- NOT provide definitive legal, tax, or immigration advice.
- Prefer actionable next steps (verify with DSO, payroll, IRS instructions, or a qualified professional when appropriate).
- Use the source URLs below only as citations when relevant; do not invent links.

Disclosure to include verbatim in the JSON field disclaimer (exact text):
"{DISCLAIMER_TEXT}"

Normalized scenario (JSON):
{json.dumps(normalized, ensure_ascii=False)}

Pipeline context:
- Topic: {context.get("pipeline_topic")}
- Topic angle: {context.get("topic_angle")}
- Platform: {context.get("platform")}
- User profile hints: {json.dumps(context.get("user_profile") or {}, ensure_ascii=False)}

Approved source links (cite only these when useful):
{src_lines or "(none)"}

Brief retrieval snippets (may be truncated):
{context.get("grounding_snippets") or "(none)"}

Return ONLY valid JSON with this shape:
{{
  "summary": "short plain English overview",
  "what_likely_applies": ["bullet as string", "..."],
  "recommended_next_steps": ["step 1", "..."],
  "watchouts": ["caveat or risk flag", "..."],
  "questions_to_confirm": ["clarifying question", "..."],
  "sources": [{{"title": "string", "url": "must be from approved list above"}}],
  "confidence": "low" | "medium" | "high",
  "disclaimer": "{DISCLAIMER_TEXT}"
}}

If no approved sources apply, use an empty sources array. Do not add markdown outside JSON."""


# ---------------------------------------------------------------------------
# Fallback guidance (no model / parse failure)
# ---------------------------------------------------------------------------

def generate_guidance_fallback(normalized: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    visa = str(normalized.get("visa_status", "unknown"))
    rh = normalized.get("rules_hints") or {}
    steps: list[str] = [
        "Confirm your visa status and work authorization with your school DSO or responsible officer before making employment or tax decisions.",
        "Gather documents: passport, I-20 or DS-2019, any W-2s/1099s, scholarship letters, and prior tax filings if applicable.",
        "Use official IRS and DHS/USCIS guidance for forms and definitions; consider a qualified tax professional for your situation.",
    ]
    watch: list[str] = [
        "Rules vary by year, treaty, and individual facts — timelines and residency tests matter.",
        DISCLAIMER_TEXT,
    ]
    if rh.get("form_8843_possible"):
        watch.append(
            "Many students in F/J status may need to consider Form 8843 for certain years — verify eligibility in current IRS instructions."
        )
    if rh.get("form_1040_nr_review"):
        watch.append("W-2 income often means reviewing whether Form 1040-NR (or other forms) applies — depends on residency status.")
    if rh.get("scholarship_portion_watchout"):
        watch.append("Scholarship/fellowship amounts may be partly taxable — allocation depends on qualified expenses vs. non-qualified uses.")
    if rh.get("1099_complexity_watchout"):
        watch.append("1099 income can involve contractor classification and work authorization questions — do not assume it is treated like W-2 wages.")

    applies = [
        f"Your described visa context ({visa}) may intersect with payroll withholding, tax residency rules, and school reporting obligations.",
    ]
    if normalized.get("needs_itin"):
        applies.append("If you have U.S. tax reporting obligations and no SSN, an ITIN application may be relevant — follow IRS Form W-7 instructions.")

    qs = list(normalized.get("missing_info") or [])[:5]
    if not qs:
        qs = [
            "What is your tax residency status for the year (often a Substantial Presence / exempt-individual analysis)?",
            "What income types did you receive (W-2, 1099, scholarship, campus payroll)?",
        ]

    summary = (
        "Here is a cautious, general read of your scenario based on what you shared. "
        "Specific tax and immigration outcomes depend on documents and timing — verify with official sources or a professional."
    )

    src_objs = list(context.get("sources") or [])[:MAX_SOURCES]

    return {
        "summary": summary,
        "what_likely_applies": applies,
        "recommended_next_steps": steps,
        "watchouts": watch,
        "questions_to_confirm": qs,
        "sources": src_objs,
        "confidence": "low",
        "disclaimer": DISCLAIMER_TEXT,
    }


def _normalize_guidance_dict(raw: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Ensure lists and disclaimer; filter sources to allowed URLs."""
    allowed = {s["url"] for s in (context.get("sources") or []) if s.get("url")}
    sources_out: list[dict[str, str]] = []
    for s in raw.get("sources") or []:
        if not isinstance(s, dict):
            continue
        u = (s.get("url") or "").strip()
        t = (s.get("title") or "Source").strip()
        if u in allowed:
            sources_out.append({"title": t, "url": u})

    def as_list(key: str) -> list[str]:
        v = raw.get(key)
        if isinstance(v, list):
            return [str(x) for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    conf = str(raw.get("confidence") or "medium").lower()
    if conf not in ("low", "medium", "high"):
        conf = "medium"

    return {
        "summary": str(raw.get("summary") or "").strip() or "See sections below for a cautious overview.",
        "what_likely_applies": as_list("what_likely_applies"),
        "recommended_next_steps": as_list("recommended_next_steps"),
        "watchouts": as_list("watchouts"),
        "questions_to_confirm": as_list("questions_to_confirm"),
        "sources": sources_out,
        "confidence": conf,
        "disclaimer": raw.get("disclaimer") or DISCLAIMER_TEXT,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_agent5(
    user_query: str,
    retrieval_pack: dict | None = None,
    content_draft: dict | None = None,
    user_profile: dict | None = None,
) -> dict[str, Any]:
    """
    Run two-stage scenario resolution. Never raises; always returns a dict with guidance schema.
    """
    try:
        return _run_agent5_impl(user_query, retrieval_pack, content_draft, user_profile)
    except Exception as exc:
        print(f"[agent5] run_agent5 error (using full fallback): {exc}")
        uq = (user_query or "").strip()
        fb_s = apply_scenario_rules(fallback_extract_scenario(uq), uq)
        ctx = extract_agent5_context(retrieval_pack, content_draft, user_profile)
        g = generate_guidance_fallback(fb_s, ctx)
        conf = g.pop("confidence", "low")
        g.pop("disclaimer", None)
        return {
            "normalized_scenario": fb_s,
            "guidance": g,
            "confidence": conf,
            "disclaimer": DISCLAIMER_TEXT,
            "meta": {
                "extraction_source": "fallback",
                "guidance_source": "fallback",
                "error": str(exc)[:200],
            },
        }


def _run_agent5_impl(
    user_query: str,
    retrieval_pack: dict | None,
    content_draft: dict | None,
    user_profile: dict | None,
) -> dict[str, Any]:
    uq = (user_query or "").strip()
    if not uq:
        empty_g = generate_guidance_fallback(
            apply_scenario_rules(fallback_extract_scenario(""), ""),
            extract_agent5_context(retrieval_pack, content_draft, user_profile),
        )
        conf = empty_g.pop("confidence", "low")
        empty_g.pop("disclaimer", None)
        return {
            "normalized_scenario": apply_scenario_rules(fallback_extract_scenario(""), ""),
            "guidance": empty_g,
            "confidence": conf,
            "disclaimer": DISCLAIMER_TEXT,
            "meta": {
                "extraction_source": "fallback",
                "guidance_source": "fallback",
                "note": "empty query",
            },
        }

    context = extract_agent5_context(retrieval_pack, content_draft, user_profile)
    fb = fallback_extract_scenario(uq)

    extraction_source = "fallback"
    raw_ex = _safe_generate(_extract_prompt(uq))
    model_ex = _parse_json_response(raw_ex) if raw_ex else {}
    if model_ex:
        extraction_source = "model"

    merged = _merge_scenario(model_ex, fb)
    normalized = apply_scenario_rules(merged, uq)

    guidance_source = "model"
    raw_g = _safe_generate(_guidance_prompt(normalized, context))
    gdict = _parse_json_response(raw_g) if raw_g else {}

    if not gdict.get("summary") and not gdict.get("what_likely_applies"):
        gdict = generate_guidance_fallback(normalized, context)
        guidance_source = "fallback"
    else:
        gdict = _normalize_guidance_dict(gdict, context)
        if not gdict.get("what_likely_applies"):
            fb_g = generate_guidance_fallback(normalized, context)
            gdict["what_likely_applies"] = fb_g.get("what_likely_applies", [])
            if not gdict.get("recommended_next_steps"):
                gdict["recommended_next_steps"] = fb_g.get("recommended_next_steps", [])
            guidance_source = "merged"

    gdict["disclaimer"] = DISCLAIMER_TEXT

    confidence = gdict.pop("confidence", "medium")
    gdict.pop("disclaimer", None)
    meta = {
        "extraction_source": extraction_source,
        "guidance_source": guidance_source,
    }

    return {
        "normalized_scenario": normalized,
        "guidance": {
            "summary": gdict.get("summary", ""),
            "what_likely_applies": gdict.get("what_likely_applies", []),
            "recommended_next_steps": gdict.get("recommended_next_steps", []),
            "watchouts": gdict.get("watchouts", []),
            "questions_to_confirm": gdict.get("questions_to_confirm", []),
            "sources": gdict.get("sources", []),
        },
        "confidence": confidence,
        "disclaimer": DISCLAIMER_TEXT,
        "meta": meta,
    }
