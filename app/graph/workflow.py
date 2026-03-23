from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import router_node, query_builder_node, query_executor_node, responder_node

workflow = StateGraph(AgentState)

workflow.add_node("router",         router_node)
workflow.add_node("query_builder",  query_builder_node)
workflow.add_node("query_executor", query_executor_node)
workflow.add_node("responder",      responder_node)

workflow.set_entry_point("router")

def _route(x):
    tasks  = x.get("tasks") or []
    intent = tasks[0].get("intent","unknown") if tasks else "unknown"
    # conversation and unknown skip DB entirely
    if intent in ("unknown","conversation"):
        return "responder"
    return "query_builder"

workflow.add_conditional_edges(
    "router",
    _route,
    {"query_builder": "query_builder", "responder": "responder"}
)

workflow.add_edge("query_builder",  "query_executor")
workflow.add_edge("query_executor", "responder")
workflow.add_edge("responder",      END)

hisabbot_agent = workflow.compile()