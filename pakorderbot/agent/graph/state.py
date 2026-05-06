from typing import TypedDict, Dict, Any, List, Optional


class AgentState(TypedDict):
    user_message:          str
    conversation_history:  List[Dict[str, str]]   # FULL history kept all session
    tasks:                 List[Dict[str, Any]]
    intent:                str
    action:                str
    entities:              Dict[str, Any]
    extracted_intent:      Dict[str, Any]
    query_plan:            Dict[str, Any]
    all_plans:             List[Dict[str, Any]]
    db_result:             str
    final_response:        str
    user_role:             str                    # "customer" | "staff" — JWT only
    order_draft:           Dict[str, Any]         # pending order
    conv_stage:            str                    # "" | "await_more" | "await_name" | "await_phone" | "await_address" | "await_confirm"
    res_type:              Optional[str]          # "bill" | "menu" | "offers"
    res_data:              Optional[Dict[str, Any]]