from app.agent.prompt_loader import load_prompt
from app.agent.state import AttachmentInput, PlannerOutput
from app.llm.base import LLMProvider
from app.llm.schemas import StructuredResult


async def plan(
    llm: LLMProvider, model: str, query: str, attachments: list[AttachmentInput] | None = None
) -> StructuredResult[PlannerOutput]:
    prompt = load_prompt("planner").format(
        query=query, attachments=_format_attachments(attachments or [])
    )
    messages = [{"role": "system", "content": prompt}]
    return await llm.structured(model=model, messages=messages, response_model=PlannerOutput)


def _format_attachments(attachments: list[AttachmentInput]) -> str:
    if not attachments:
        return ""
    names = ", ".join(a.filename for a in attachments)
    return (
        f"\nThe user also attached {len(attachments)} document(s) already available as "
        f"evidence for the synthesis stage: {names}. Plan sub-questions that make good use "
        "of them alongside web research where relevant."
    )
