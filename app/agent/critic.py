from app.agent.prompt_loader import load_prompt
from app.agent.state import CriticVerdict, EvidenceStore
from app.llm.base import LLMProvider
from app.llm.schemas import StructuredResult


async def critique(
    llm: LLMProvider,
    model: str,
    query: str,
    sub_questions: list[str],
    evidence: EvidenceStore,
) -> StructuredResult[CriticVerdict]:
    prompt = load_prompt("critic").format(
        query=query,
        sub_questions="\n".join(f"- {q}" for q in sub_questions),
        evidence=evidence.as_prompt_block(),
    )
    messages = [{"role": "system", "content": prompt}]
    return await llm.structured(model=model, messages=messages, response_model=CriticVerdict)
