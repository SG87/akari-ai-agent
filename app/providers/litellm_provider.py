"""
LiteLLM provider — unified LLM backend with Langfuse tracing.

Uses litellm.acompletion() to call any LLM provider (Anthropic, OpenAI,
Google, Mistral, etc.) through a single OpenAI-compatible interface.
The model string determines which provider API is called.

Anthropic prompt caching
~~~~~~~~~~~~~~~~~~~~~~~~
For Anthropic models, cache_control breakpoints are placed on:
  1. The system prompt  — large, identical for the same skill set
  2. The last tool def  — stable across all requests
Cached input tokens are billed at ~10% of normal cost. On multi-turn
agent loops this typically saves 50-90% of input costs because the
system prompt + tools prefix is resent verbatim every iteration.
"""

import asyncio
import copy
import json
import logging
import uuid

import litellm

from app.providers.base import AgentResponse
from app.tools.registry import execute_tool

logger = logging.getLogger("akari.provider.litellm")

# Safety limit to prevent infinite tool-use loops
_MAX_ITERATIONS = 15

# Anthropic cache_control marker
_CACHE_EPHEMERAL = {"type": "ephemeral"}


def _is_anthropic(model: str) -> bool:
    """Check if the model string targets Anthropic."""
    return model.startswith("anthropic/")


def _build_system_message(system_prompt: str, *, use_cache: bool) -> dict:
    """Build the system message, optionally with a cache breakpoint."""
    if use_cache:
        # Anthropic expects content as a list of typed blocks
        return {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": _CACHE_EPHEMERAL,
                }
            ],
        }
    return {"role": "system", "content": system_prompt}


def _add_tool_cache_breakpoint(tools: list[dict]) -> list[dict]:
    """Return a copy of tools with a cache breakpoint on the last entry.

    Anthropic caches the entire prefix up to the breakpoint, so placing
    it on the *last* tool definition caches the full tools array.
    """
    if not tools:
        return tools
    tools = copy.deepcopy(tools)
    tools[-1]["function"]["cache_control"] = _CACHE_EPHEMERAL
    return tools


async def run_agent_loop(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    model: str,
    trace_context: dict | None = None,
) -> AgentResponse:
    """Run the tool-use agent loop via LiteLLM.

    Calls litellm.acompletion() in a loop, executing tool calls until the
    model produces a final text response or the iteration limit is reached.

    Args:
        system_prompt: Assembled system instructions.
        messages: Conversation history [{role, content}, ...].
        tools: Tool schemas in OpenAI function-calling format.
        model: LiteLLM model string (e.g. 'anthropic/claude-opus-4-0',
               'gpt-4o', 'gemini/gemini-2.5-pro').
        trace_context: Optional Langfuse tracing context with keys:
            trace_id, session_id, tenant_id, tier.

    Returns:
        AgentResponse with the final text, tools called, and usage stats.
    """
    tool_calls_made: list[str] = []
    total_usage: dict = {"inputTokens": 0, "outputTokens": 0}
    iteration = 0

    # Enable prompt caching for Anthropic models
    use_cache = _is_anthropic(model)

    # Build messages with system prompt prepended
    working_messages: list[dict] = [
        _build_system_message(system_prompt, use_cache=use_cache),
    ]
    working_messages.extend(messages)

    # Prepare tools (with optional cache breakpoint on last entry)
    effective_tools = _add_tool_cache_breakpoint(tools) if use_cache and tools else tools

    # Build Langfuse metadata (ignored if Langfuse callbacks are not active)
    trace_ctx = trace_context or {}
    base_metadata: dict = {
        "trace_id": trace_ctx.get("trace_id", str(uuid.uuid4())),
        "trace_name": "akari-chat",
        "session_id": trace_ctx.get("session_id"),
        "trace_user_id": trace_ctx.get("tenant_id"),
        "tags": [
            f"tier:{trace_ctx.get('tier', 'unknown')}",
            f"model:{model}",
        ],
    }

    if use_cache:
        logger.info("CACHE | Anthropic prompt caching enabled for model=%s", model)

    while iteration < _MAX_ITERATIONS:
        iteration += 1
        logger.info(
            "AGENT_ITERATION | iteration=%d | model=%s | messages=%d",
            iteration, model, len(working_messages),
        )

        # Build metadata for this specific generation
        metadata = {
            **base_metadata,
            "generation_name": f"agent-iteration-{iteration}",
        }

        response = await litellm.acompletion(
            model=model,
            messages=working_messages,
            tools=effective_tools if effective_tools else None,
            max_tokens=8192,
            metadata=metadata,
        )

        choice = response.choices[0]

        # Accumulate token usage
        if response.usage:
            total_usage["inputTokens"] += response.usage.prompt_tokens
            total_usage["outputTokens"] += response.usage.completion_tokens

            # Log cache stats when available (Anthropic returns these)
            cache_read = getattr(response.usage, "cache_read_input_tokens", None)
            cache_create = getattr(response.usage, "cache_creation_input_tokens", None)
            if cache_read or cache_create:
                total_usage["cacheReadInputTokens"] = (
                    total_usage.get("cacheReadInputTokens", 0) + (cache_read or 0)
                )
                total_usage["cacheCreationInputTokens"] = (
                    total_usage.get("cacheCreationInputTokens", 0) + (cache_create or 0)
                )
                logger.info(
                    "CACHE_STATS | iteration=%d | cache_read=%s | cache_create=%s",
                    iteration, cache_read, cache_create,
                )

        # Check if the model wants to call tools
        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            # Append assistant message with tool calls
            working_messages.append(choice.message.model_dump())

            async def _run_tool(tool_call):
                fn = tool_call.function
                logger.info("TOOL_USE | name=%s | id=%s", fn.name, tool_call.id)
                tool_calls_made.append(fn.name)

                try:
                    tool_input = json.loads(fn.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                result = await execute_tool(fn.name, tool_input)
                return {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }

            tool_results = await asyncio.gather(
                *[_run_tool(tc) for tc in choice.message.tool_calls]
            )

            working_messages.extend(tool_results)

        else:
            # Final response — extract text
            final_text = choice.message.content or ""

            logger.info(
                "AGENT_DONE | iterations=%d | tools_called=%s | usage=%s | reply_length=%d",
                iteration, tool_calls_made, total_usage, len(final_text),
            )

            return AgentResponse(
                text=final_text,
                model=model,
                tool_calls=tool_calls_made,
                usage=total_usage,
                iterations=iteration,
            )

    # Safety: max iterations reached
    logger.warning("AGENT_MAX_ITERATIONS | iterations=%d", iteration)
    return AgentResponse(
        text="I apologize, but I've reached the maximum number of tool iterations. "
             "Could you try a more specific request?",
        model=model,
        tool_calls=tool_calls_made,
        usage=total_usage,
        iterations=iteration,
    )
