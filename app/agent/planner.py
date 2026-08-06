from app.agent.prompt_loader import load_prompt
from app.agent.state import PlannerOutput
from app.llm.client import LLMClient
from app.llm.schemas import StructuredResult


async def plan(llm: LLMClient, model: str, query: str) -> StructuredResult[PlannerOutput]:
    prompt = load_prompt("planner").format(query=query)
    messages = [{"role": "system", "content": prompt}]
    return await llm.structured(model=model, messages=messages, response_model=PlannerOutput)
