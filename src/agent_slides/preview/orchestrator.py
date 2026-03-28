"""Compatibility re-export for the unified orchestrator module."""

from __future__ import annotations

from agent_slides.orchestrator import (
    ChatResponse,
    DeckConversationOrchestrator,
    DeckOrchestrator,
    DEFAULT_MODEL,
    OrchestratorConfig,
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
)

__all__ = [
    "ChatResponse",
    "DeckConversationOrchestrator",
    "DeckOrchestrator",
    "DEFAULT_MODEL",
    "OrchestratorConfig",
    "SYSTEM_PROMPT",
    "TOOL_DEFINITIONS",
]
