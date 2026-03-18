"""
HisabBot Workflow — v5 (Fully Dynamic)

Single pipeline for everything:
  router_node → query_builder_node → query_executor_node → responder_node
"""
from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import router_node, query_builder_node, query_executor_node, responder_node

workflow = StateGraph(AgentState)

workflow.add_node("router",          router_node)
workflow.add_node("query_builder",   query_builder_node)
workflow.add_node("query_executor",  query_executor_node)
workflow.add_node("responder",       responder_node)

workflow.set_entry_point("router")

# Route: unknown goes straight to responder, everything else builds a query
workflow.add_conditional_edges(
    "router",
    lambda x: "responder" if x["intent"] == "unknown" else "query_builder",
    {
        "query_builder": "query_builder",
        "responder":     "responder",
    }
)

workflow.add_edge("query_builder",  "query_executor")
workflow.add_edge("query_executor", "responder")
workflow.add_edge("responder",      END)

hisabbot_agent = workflow.compile()