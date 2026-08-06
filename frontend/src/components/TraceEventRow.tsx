import type { JobEventMessage } from "../api/types";
import { describeEvent } from "../lib/traceEvents";

const ICONS: Record<string, string> = {
  phase_change: "▸", // ▸
  llm_call: "✦", // ✦
  tool_call: "→", // →
  tool_result: "✓", // ✓
  error: "✕", // ✕
};

export function TraceEventRow({ message }: { message: JobEventMessage }) {
  const isError = message.event === "error";
  return (
    <li className={`flex gap-2 py-1 text-xs ${isError ? "text-red-600" : "text-stone-500"}`}>
      <span className="w-3 shrink-0 text-center">{ICONS[message.event] ?? "•"}</span>
      <span className="break-words">{describeEvent(message)}</span>
    </li>
  );
}
