from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    """Prompts live as versionable, diffable Markdown files rather than
    inline strings -- this is what lets a prompt change show up cleanly in
    a PR diff and be referenced by filename in an eval regression report."""
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
