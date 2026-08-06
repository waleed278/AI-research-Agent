import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ResearchResultResponse } from "../api/types";
import { linkifyCitations, sourceAnchorId } from "../lib/citations";

export function ReportView({ result }: { result: ResearchResultResponse }) {
  return (
    <div className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
      <div className="prose max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {linkifyCitations(result.report_markdown)}
        </ReactMarkdown>
      </div>

      {result.sources.length > 0 && (
        <div className="mt-6 border-t border-stone-100 pt-4">
          <h3 className="text-sm font-semibold text-stone-700">Sources</h3>
          <ol className="mt-2 space-y-1">
            {result.sources.map((source) => (
              <li key={source.id} id={sourceAnchorId(source.id)} className="scroll-mt-4 text-sm">
                <span className="text-stone-400">[{source.id}]</span>{" "}
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-indigo-600 underline decoration-indigo-300 underline-offset-2 hover:text-indigo-800"
                >
                  {source.title || source.url}
                </a>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
