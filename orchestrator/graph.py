from typing import Any
from typing_extensions import TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

import agents.language_agent as language_agent
import agents.profile_agent as profile_agent
import agents.pattern_agent as pattern_agent
import agents.nudge_agent as nudge_agent


# Shared state 


class AgentState(TypedDict):
    """
    Shared state object passed through every node in the LangGraph pipeline.

    Agents read from this dict and return an updated copy.
    Only the keys a particular agent cares about need to be touched.
    """

    # Incoming message
    user_id: str                   # WhatsApp phone number (E.164)
    raw_message: str               # original text from user (or empty if voice)
    message_type: str              # "text" | "audio"
    audio_bytes: bytes | None      # raw OGG bytes for voice messages
    audio_mime_type: str           # default "audio/ogg"

    # Language Agent (first pass)
    detected_language: str         # BCP-47 code e.g. "hi", "mr", "kn"
    translated_message: str        # English translation of the user's message

    # Profile Agent
    profile: dict[str, Any]        # serialised UserProfile snapshot
    extracted_events: list[dict]   # financial events parsed from this message

    # Pattern Agent
    risk_flags: list[str]          # e.g. ["overspending", "predatory_loan"]
    interrupt: bool                # True → Pattern Agent bypasses Nudge Agent

    # Nudge Agent
    nudge_type: str | None         # e.g. "savings_nudge", "loan_warning"
    nudge_content: str | None      # English nudge text
    seekho_content: str | None     # English micro-lesson text

    # Language Agent (second pass)
    final_response: str            # assembled English response (nudge + seekho)
    final_response_translated: str # response in user's language → sent to WhatsApp


# Routing

def _route_after_pattern(state: AgentState) -> str:
    """
    After the Pattern Agent runs:
    - interrupt=True  → skip Nudge Agent, go straight to outgoing translation
    - interrupt=False → proceed to Nudge Agent
    """
    return "language_out" if state.get("interrupt") else "nudge"


# Graph definition 


def build_graph() -> StateGraph:
    """Construct and return the compiled LangGraph StateGraph."""

    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("language_in",  language_agent.run_incoming)
    graph.add_node("profile",      profile_agent.run)
    graph.add_node("pattern",      pattern_agent.run)
    graph.add_node("nudge",        nudge_agent.run)
    graph.add_node("language_out", language_agent.run_outgoing)

    # Entry point
    graph.set_entry_point("language_in")

    # Fixed edges
    graph.add_edge("language_in", "profile")
    graph.add_edge("profile",     "pattern")
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

    # MemorySaver keeps state in memory for the duration of a single pipeline run.
    # thread_id = user's WhatsApp phone number → each user gets isolated state.
    # For production persistence across server restarts, replace with a
    # Redis-backed checkpointer (langgraph-checkpoint-redis).
    checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)


# Module-level compiled graph — imported by the FastAPI webhook
app = build_graph()
