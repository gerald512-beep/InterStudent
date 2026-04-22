"""
Audience / persona merge helpers for Agent 2, Creative Storyteller, and UI.
"""


def merge_retrieval_persona(base: dict | None, user: dict | None) -> dict:
    """Overlay UI persona fields onto Agent 1 defaults."""
    base = base or {}
    user = user or {}
    return {**base, **user}


def persona_prompt_block(persona: dict | None) -> str:
    """Rich instruction block for Gemini prompts (post + video brief)."""
    if not persona:
        return ""

    def _line(label: str, key: str) -> str:
        v = persona.get(key)
        if v is None or v == "" or v == []:
            return ""
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v)
        return f"- {label}: {v}"

    parts = [
        _line("Persona name", "persona_name"),
        _line("Audience segment", "audience_segment"),
        _line("City focus", "city_focus"),
        _line("School type", "school_type"),
        _line("Content goals", "content_goal"),
        _line("Tone preference", "tone_preference"),
        _line("Platform style", "platform_style"),
        _line("CTA preference", "cta_preference"),
        _line("Risk tolerance", "risk_tolerance"),
        _line("Avatar style", "avatar_style"),
        _line("Language support", "include_language_support"),
        _line("Languages", "languages"),
    ]
    text = "\n".join(p for p in parts if p)
    if not text.strip():
        return ""
    return (
        "AUDIENCE PERSONALIZATION (follow closely — adapt hook, CTA, storyboard beats, and tone):\n"
        + text
    )


def effective_tone(persona: dict | None) -> str:
    if not persona:
        return "helpful"
    return str(
        persona.get("tone_preference")
        or persona.get("tone")
        or "helpful"
    )


def effective_audience_line(persona: dict | None) -> str:
    if not persona:
        return "international students in NYC"
    seg = persona.get("audience_segment") or persona.get("audience") or "international students"
    city = persona.get("city_focus") or "NYC"
    school = persona.get("school_type") or ""
    bits = [seg, f"focus: {city}"]
    if school and school != "Any":
        bits.append(f"education level: {school}")
    return "; ".join(bits)


def interleaved_persona_hint(persona: dict | None) -> str:
    if not persona:
        return ""
    goals = persona.get("content_goal") or []
    goals_s = ", ".join(goals) if goals else ""
    return (
        f"Tone: {effective_tone(persona)}. "
        f"Audience: {effective_audience_line(persona)}. "
        f"Platform style: {persona.get('platform_style', '')}. "
        f"CTA style: {persona.get('cta_preference', '')}. "
        f"Goals: {goals_s}. "
        f"Risk tolerance: {persona.get('risk_tolerance', '')}."
    ).strip()
