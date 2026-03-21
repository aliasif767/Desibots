"""
HisabBot Workflow — v6 (Specialized Query Builders)

Single pipeline:
  router → query_builder (dispatches to specialized builders in parallel) → query_executor → responder
"""
from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import router_node, query_builder_node, query_executor_node, responder_node

workflow = StateGraph(AgentState)

workflow.add_node("router",         router_node)
workflow.add_node("query_builder",  query_builder_node)
workflow.add_node("query_executor", query_executor_node)
workflow.add_node("responder",      responder_node)

workflow.set_entry_point("router")

workflow.add_conditional_edges(
    "router",
    lambda x: "responder" if (
        x.get("tasks") and
        x["tasks"][0].get("intent") == "unknown" and
        len(x["tasks"]) == 1
    ) else "query_builder",
    {"query_builder": "query_builder", "responder": "responder"}
)

workflow.add_edge("query_builder",  "query_executor")
workflow.add_edge("query_executor", "responder")
workflow.add_edge("responder",      END)

hisabbot_agent = workflow.compile()