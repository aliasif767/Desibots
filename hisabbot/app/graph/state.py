from typing import TypedDict, Dict, Any, List, Optional

class AgentState(TypedDict):
    user_message:          str
    conversation_history:  List[Dict[str, str]]  # [{role: user/assistant, content: ...}]
    tasks:                 List[Dict[str, Any]]
    intent:                str
    action:                str
    entities:              Dict[str, Any]
    extracted_intent:      Dict[str, Any]
    query_plan:            Dict[str, Any]
    all_plans:             List[Dict[str, Any]]
    db_result:             str
    final_response:        str