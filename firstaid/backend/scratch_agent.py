import asyncio
from app.agents.staff_agent import _get_llm, STAFF_AGENT_SYSTEM
from langchain_core.messages import SystemMessage, HumanMessage

async def main():
    llm = _get_llm(temperature=0.0)
    messages = [
        SystemMessage(content=STAFF_AGENT_SYSTEM),
        HumanMessage(content="Staff message: Add Dr. Ali, General Physician, 9am-5pm")
    ]
    response = await llm.ainvoke(messages)
    print("RAW LLM OUTPUT:")
    print(response.content)

if __name__ == "__main__":
    asyncio.run(main())
