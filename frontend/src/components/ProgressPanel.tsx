import { useEffect, useRef } from "react";

import type { JobEventMessage, JobPhase } from "../api/types";
import { PHASE_LABELS, PHASE_ORDER } from "../lib/traceEvents";
import { TraceEventRow } from "./TraceEventRow";

interface ProgressPanelProps {
  phase: JobPhase | null;
  events: JobEventMessage[];
}

export function ProgressPanel({ phase, events }: ProgressPanelProps) {
  const logRef = useRef<HTMLUListElement>(null);
  const currentIndex = phase ? PHASE_ORDER.indexOf(phase) : -1;

  useEffect(() => {
    const log = logRef.current;
    // Guarded rather than assumed: jsdom (used by the component tests)
    // doesn't implement scrollTo, and a defensive check here is cheap.
    if (log && typeof log.scrollTo === "function") {
      log.scrollTo({ top: log.scrollHeight });
    }
  }, [events.length]);

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      <ol className="flex items-center">
        {PHASE_ORDER.filter((p) => p !== "done").map((p, index) => {
          const isActive = index === currentIndex;
          const isComplete = currentIndex > index;
          return (
            <li key={p} className="flex flex-1 items-center last:flex-none">
              <div className="flex items-center gap-2">
                <span
                  className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-medium ${
                    isComplete
                      ? "bg-indigo-600 text-white"
                      : isActive
                        ? "border-2 border-indigo-600 text-indigo-600"
                        : "border border-stone-300 text-stone-400"
                  }`}
                >
                  {isComplete ? "✓" : index + 1}
                </span>
                <span
                  className={`text-xs ${isActive ? "font-medium text-stone-800" : "text-stone-400"}`}
                >
                  {PHASE_LABELS[p]}
                </span>
              </div>
              {index < PHASE_ORDER.length - 2 && (
                <div className={`mx-2 h-px flex-1 ${isComplete ? "bg-indigo-600" : "bg-stone-200"}`} />
              )}
            </li>
          );
        })}
      </ol>

      <ul ref={logRef} className="mt-4 max-h-64 space-y-0.5 overflow-y-auto border-t border-stone-100 pt-3">
        {events.length === 0 && <li className="text-xs text-stone-400">Waiting for the agent to start...</li>}
        {events.map((message, index) => (
          <TraceEventRow key={index} message={message} />
        ))}
      </ul>
    </div>
  );
}
