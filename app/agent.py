"""
Agent — Anthropic tool-use loop for the Akari Scout AI.

Executes the standard tool-use cycle:
1. Send messages + tools to Anthropic
2. If the model requests tool use → execute tools, append results, loop
3. If the model produces a final response → return it
"""

import logging
from dataclasses import dataclass, field

import anthropic

from app.config import settings
from app.tools.registry import execute_tool

logger = logging.getLogger("akari.agent")

# Safety limit to prevent infinite tool-use loops
_MAX_ITERATIONS = 15


@dataclass
class AgentResponse:
    """Result of an agent invocation."""

    text: str
    model: str
    tool_calls: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    iterations: int = 0


async def run_agent(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    model: str,
) -> AgentResponse:
    """Run the Anthropic tool-use agent loop.

    Args:
        system_prompt: The assembled system prompt (from skills).
        messages: Conversation history in Anthropic format
                  [{"role": "user"|"assistant", "content": "..."}].
        tools: Tool schemas in Anthropic format.
        model: Anthropic model ID to use.

    Returns:
        AgentResponse with the final text, tools called, and usage stats.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    tool_calls_made: list[str] = []
    total_usage: dict = {"input_tokens": 0, "output_tokens": 0}
    iteration = 0

    # Working copy of messages — we'll append tool results as we loop
    working_messages = list(messages)

    while iteration < _MAX_ITERATIONS:
        iteration += 1
        logger.info(
            "AGENT_ITERATION | iteration=%d | model=%s | messages=%d",
            iteration, model, len(working_messages),
        )

        response = await client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=working_messages,
            tools=tools if tools else anthropic.NOT_GIVEN,
        )

        # Accumulate token usage
        if response.usage:
            total_usage["input_tokens"] += response.usage.input_tokens
            total_usage["output_tokens"] += response.usage.output_tokens

        # Check stop reason
        if response.stop_reason == "tool_use":
            # Extract tool use blocks and execute them
            assistant_content = response.content
            working_messages.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_id = block.id

                    logger.info("TOOL_USE | name=%s | id=%s", tool_name, tool_id)
                    tool_calls_made.append(tool_name)

                    result = await execute_tool(tool_name, tool_input)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result,
                    })

            working_messages.append({"role": "user", "content": tool_results})

        else:
            # Final response — extract text
            text_parts: list[str] = []
            for block in response.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)

            final_text = "\n".join(text_parts)

            logger.info(
                "AGENT_DONE | iterations=%d | tools_called=%s | usage=%s | reply_length=%d",
                iteration,
                tool_calls_made,
                total_usage,
                len(final_text),
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
