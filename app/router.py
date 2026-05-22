"""
Router — Haiku-based request classifier for model and skill selection.

Classifies incoming user messages by complexity to select:
1. Which Anthropic model to use (Haiku / Sonnet / Opus)
2. Which skill files to inject into the system prompt
3. A suggested session label (for the first message in a new session)
"""

import json
import logging
from dataclasses import dataclass, field

import anthropic

from app.config import settings

logger = logging.getLogger("akari.router")


@dataclass
class RouterResult:
    """Result of the request classification."""

    model: str
    skills: list[str]
    suggested_label: str | None = None
    tier: str = "STANDARD"


# ── Model mapping ─────────────────────────────────────────────────────────

_TIER_MODELS = {
    "SIMPLE": "claude-haiku-4-0",
    "STANDARD": "claude-sonnet-4-20250514",
    "COMPLEX": settings.DEFAULT_MODEL,  # claude-opus-4-0
}

_CLASSIFIER_PROMPT = """\
You are a request classifier for a football scouting AI called Akari Scout.

Classify the user's message into one of these tiers:

- SIMPLE: Greetings, clarifications, follow-up questions, thank you messages, \
single player name lookups, status checks, simple yes/no answers. \
No tools needed or at most one simple lookup.

- STANDARD: Player searches with clear parameters, player profile requests, \
comparisons between 2 players, stat leader queries. Requires tool use but \
the intent is clear and well-scoped.

- COMPLEX: Multi-step scouting workflows, vague or underspecified requests \
needing clarification, market/league analysis, replacement player searches \
(finding alternatives for a departing player), requests spanning multiple \
leagues or positions, anything requiring strategic reasoning.

Also identify which skills are needed:
- "scout-search": when the user wants to FIND or DISCOVER players (search, shortlist, replacements)
- "scout-analysis": when the user wants to ANALYZE specific players (deep dive, compare, market overview)
- Both can be selected if the request spans search and analysis.
- Use an empty list if no scouting skill is needed (e.g. greetings).

Finally, generate a short label (max 5 words) summarizing the user's intent. \
This will be used as the session title. Examples: "U21 Left Wingers South America", \
"Compare CB options Belgium", "Market overview Croatian league".

Respond with ONLY a JSON object, no other text:
{"tier": "SIMPLE|STANDARD|COMPLEX", "skills": [...], "label": "..."}
"""


async def classify(
    user_message: str,
    conversation_history: list[dict] | None = None,
) -> RouterResult:
    """Classify a user message to determine model, skills, and session label.

    Args:
        user_message: The latest user message.
        conversation_history: Optional prior messages for context.

    Returns:
        RouterResult with model, skills, suggested_label, and tier.
    """
    # Build the classifier messages
    messages = [{"role": "user", "content": user_message}]

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=settings.ROUTER_MODEL,
            max_tokens=256,
            system=_CLASSIFIER_PROMPT,
            messages=messages,
        )

        # Parse the JSON response
        raw_text = response.content[0].text.strip()

        # Handle potential markdown code block wrapping
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        result = json.loads(raw_text)

        tier = result.get("tier", "STANDARD").upper()
        if tier not in _TIER_MODELS:
            tier = "STANDARD"

        skills = result.get("skills", [])
        if not isinstance(skills, list):
            skills = []

        label = result.get("label")

        logger.info(
            "ROUTER | tier=%s | model=%s | skills=%s | label=%s",
            tier, _TIER_MODELS[tier], skills, label,
        )

        return RouterResult(
            model=_TIER_MODELS[tier],
            skills=skills,
            suggested_label=label,
            tier=tier,
        )

    except Exception as e:
        # On any failure, fall back to defaults (Opus + all skills)
        logger.warning("ROUTER_FALLBACK | error=%s — defaulting to COMPLEX", str(e))
        return RouterResult(
            model=settings.DEFAULT_MODEL,
            skills=["scout-search", "scout-analysis"],
            suggested_label=None,
            tier="COMPLEX",
        )
