"""Scene graph model package."""

from .types import (
    ComputedNode,
    ComputedDeck,
    ComputedSlide,
    Counters,
    Deck,
    GridDef,
    LayoutDef,
    Node,
    NodeContent,
    Slide,
    SlotDef,
    TextFitting,
    TextBlock,
    Theme,
    ThemeColors,
    ThemeFonts,
    ThemeSpacing,
)
from agent_slides.model.layout_provider import BuiltinLayoutProvider, LayoutProvider, resolve_layout_provider
from agent_slides.model.constraints import Constraint
from agent_slides.model.design_rules import DesignRules, list_design_rules, load_design_rules
from agent_slides.model.layouts import get_layout, list_layouts

__all__ = [
    "ComputedNode",
    "ComputedDeck",
    "ComputedSlide",
    "Constraint",
    "Counters",
    "Deck",
    "DesignRules",
    "GridDef",
    "BuiltinLayoutProvider",
    "LayoutDef",
    "LayoutProvider",
    "Node",
    "NodeContent",
    "Slide",
    "SlotDef",
    "TextFitting",
    "TextBlock",
    "Theme",
    "ThemeColors",
    "ThemeFonts",
    "ThemeSpacing",
    "get_layout",
    "list_design_rules",
    "list_layouts",
    "load_design_rules",
    "resolve_layout_provider",
]
