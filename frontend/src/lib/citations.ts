// The backend never emits citations as Markdown links -- just bare `[n]`
// referencing a source ID (see app/agent/prompts/synthesizer.md and
// evals/metrics.py, which parses reports the same way). This turns each
// one into a real link down to that source's anchor in the rendered
// Sources list, so `react-markdown` renders it as a clickable citation
// with no custom plugin needed.
//
// The negative lookahead avoids double-processing text that's already a
// Markdown link with purely numeric link text, e.g. `[1](https://x.com)`.
const CITATION_PATTERN = /\[(\d+)\](?!\()/g;

export function linkifyCitations(markdown: string): string {
  return markdown.replace(CITATION_PATTERN, (_match, id: string) => `[[${id}]](#source-${id})`);
}

export function sourceAnchorId(sourceId: number): string {
  return `source-${sourceId}`;
}
