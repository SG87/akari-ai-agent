"""
Agent — thin dispatcher that delegates to the LiteLLM provider.

Supports any LLM provider via LiteLLM model strings (e.g.
'anthropic/claude-opus-4-0', 'gpt-4o', 'gemini/gemini-2.5-pro').
"""

import logging

from app.providers.base import AgentResponse
from app.providers.litellm_provider import run_agent_loop

logger = logging.getLogger("akari.agent")


async def run_agent(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    model: str,
    trace_context: dict | None = None,
) -> AgentResponse:
    """Run the tool-use agent loop via LiteLLM.

    Args:
        system_prompt: The assembled system prompt (from skills).
        messages: Conversation history [{role, content}, ...].
        tools: Tool schemas in OpenAI function-calling format.
        model: LiteLLM model string.
        trace_context: Optional Langfuse tracing context.

    Returns:
        AgentResponse with the final text, tools called, and usage stats.
    """
    logger.info("AGENT_DISPATCH | model=%s", model)
    return await run_agent_loop(
        system_prompt, messages, tools, model, trace_context,
    )
