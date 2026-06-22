"""
LangGraph StateGraph — full pipeline wiring.

AgentState lives in orchestrator.state to avoid circular imports.
This module imports agents (which import state.py) without any cycle.

Pipeline flow (normal path):
  language_in → profile → pattern → nudge → language_out → END

Interrupt path (high-risk: predatory loan or distress signal):
  language_in → profile → pattern → language_out → END
"""

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

import agents.language_agent as language_agent
import agents.profile_agent as profile_agent
import agents.pattern_agent as pattern_agent
import agents.nudge_agent as nudge_agent

from orchestrator.state import AgentState  # re-export so callers can do: from orchestrator.graph import AgentState

__all__ = ["AgentState", "app"]


# ── Routing ───────────────────────────────────────────────────────────────────


def _route_after_pattern(state: AgentState) -> str:
    """
    After the Pattern Agent runs:
    - interrupt=True  → skip Nudge Agent, go straight to outgoing translation
    - interrupt=False → proceed to Nudge Agent
    """
    return "language_out" if state.get("interrupt") else "nudge"


# ── Graph definition ──────────────────────────────────────────────────────────


def build_graph():
    """Construct and return the compiled LangGraph StateGraph."""

    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("language_in",  language_agent.run_incoming)
    graph.add_node("profile_node", profile_agent.run)
    graph.add_node("pattern",      pattern_agent.run)
    graph.add_node("nudge",        nudge_agent.run)
    graph.add_node("language_out", language_agent.run_outgoing)

    # Entry point
    graph.set_entry_point("language_in")

    # Fixed edges
    graph.add_edge("language_in",  "profile_node")
    graph.add_edge("profile_node", "pattern")
    graph.add_edge("nudge",       "language_out")
    graph.add_edge("language_out", END)

    # Conditional edge after Pattern Agent
    graph.add_conditional_edges(
        "pattern",
        _route_after_pattern,
        {
            "nudge":        "nudge",
            "language_out": "language_out",
        },
    )

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# Module-level compiled graph — imported by the FastAPI webhook
app = build_graph()
