from app.agent.prompt_loader import load_prompt
from app.agent.state import EvidenceStore, SynthesizerOutput
from app.llm.base import LLMProvider
from app.llm.schemas import StructuredResult


async def synthesize(
    llm: LLMProvider,
    model: str,
    query: str,
    sub_questions: list[str],
    evidence: EvidenceStore,
) -> StructuredResult[SynthesizerOutput]:
    prompt = load_prompt("synthesizer").format(
        query=query,
        sub_questions="\n".join(f"- {q}" for q in sub_questions),
        evidence=evidence.as_prompt_block(),
    )
    messages = [{"role": "system", "content": prompt}]
    return await llm.structured(model=model, messages=messages, response_model=SynthesizerOutput)
