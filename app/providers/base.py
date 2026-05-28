"""
Agent response model used across the provider layer.
"""

from dataclasses import dataclass, field


@dataclass
class AgentResponse:
    """Unified result from the LLM agent loop."""

    text: str
    model: str
    tool_calls: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    iterations: int = 0
