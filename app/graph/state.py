from typing import TypedDict, Dict, Any, List

class AgentState(TypedDict):
    user_message:     str
    tasks:            List[Dict[str, Any]]  # all intents detected by router
    intent:           str                   # first task intent (compat)
    action:           str                   # first task action (compat)
    entities:         Dict[str, Any]        # first task entities (compat)
    extracted_intent: Dict[str, Any]        # full router output
    query_plan:       Dict[str, Any]        # first plan (compat)
    all_plans:        List[Dict[str, Any]]  # all tagged plans from dispatch
    db_result:        str                   # combined result string
    final_response:   str