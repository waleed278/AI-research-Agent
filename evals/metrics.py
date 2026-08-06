import re

from app.agent.state import EvidenceItem

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def citation_validity(report_markdown: str, sources: list[EvidenceItem]) -> tuple[float, int]:
    """The one metric in this suite that needs no LLM judge at all: whether
    `[n]` resolves to a real source ID is a fact, not an opinion. Returns
    (fraction_valid, total_citations_found). A report with zero citations
    scores 0.0 here -- an uncited report is exactly the failure mode this
    check exists to catch, not a vacuous pass.
    """
    valid_ids = {s.id for s in sources}
    citations = [int(match) for match in _CITATION_PATTERN.findall(report_markdown)]
    if not citations:
        return 0.0, 0
    valid = sum(1 for citation_id in citations if citation_id in valid_ids)
    return valid / len(citations), len(citations)
