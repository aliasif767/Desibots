from typing import TypedDict, Dict, Any, List

class AgentState(TypedDict):
    user_message:     str
    intent:           str            # "write" | "read" | "unknown"
    action:           str            # short description from router
    entities:         Dict[str, Any] # extracted entities from router
    extracted_intent: Dict[str, Any] # full router output
    query_plan:       Dict[str, Any] # MongoDB operation plan from query_builder
    db_result:        str            # raw result from executor
    final_response:   str            # final Roman Urdu response