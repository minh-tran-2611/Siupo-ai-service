"""
Map (tool_name, agent_label) → diagram edges.

The FE diagram (FE-admin/.../AgentDiagram.jsx) defines CONNECTIONS between
nodes. This module produces the same edge keys ("from>to") so the FE can
animate the exact lines the BE just touched.
"""
from app.tools.tool_declarations import (
    MANAGEMENT_DECLARATIONS,
    ANALYTICS_DECLARATIONS,
)


def _names_from(declarations) -> set[str]:
    out: set[str] = set()
    for tool in declarations:
        for fn in getattr(tool, "function_declarations", []) or []:
            name = getattr(fn, "name", None)
            if name:
                out.add(name)
    return out


MANAGEMENT_TOOL_NAMES: set[str] = _names_from(MANAGEMENT_DECLARATIONS)
ANALYTICS_TOOL_NAMES: set[str] = _names_from(ANALYTICS_DECLARATIONS)


def _agent_id_from_label(label: str) -> str:
    if "Management" in label:
        return "management"
    if "Analytics" in label:
        return "analytics"
    return "orchestrator"


def tool_to_edges(tool_name: str, label: str = "") -> list[tuple[str, str]]:
    """Resolve a tool invocation to one or more diagram edges.

    `label` is the caller hint set in llm_utils.execute_tool — empty for
    the orchestrator-level call site.
    """
    caller = _agent_id_from_label(label)

    # Orchestrator meta-tools that fan out to sub-agents
    if tool_name == "call_management_agent":
        return [("orchestrator", "management")]
    if tool_name == "call_analytics_agent":
        return [("orchestrator", "analytics")]

    # Shared infra tools — credit to whichever agent invoked them
    if tool_name == "search_internet":
        return [(caller, "google")]
    if tool_name == "search_documents":
        return [(caller, "qdrant")]

    # Sub-agent tools: light up <agent>>tools_<agent> bundle edge
    if tool_name in MANAGEMENT_TOOL_NAMES and caller == "management":
        return [("management", "tools_management")]
    if tool_name in ANALYTICS_TOOL_NAMES and caller == "analytics":
        return [("analytics", "tools_analytics")]

    return []


def caller_agent_id(label: str) -> str:
    """Public helper for emit sites that don't already know the agent_id."""
    return _agent_id_from_label(label)
