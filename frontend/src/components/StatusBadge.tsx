import type { JobStatus } from "../api/types";

const STYLES: Record<JobStatus, string> = {
  queued: "bg-stone-200 text-stone-700",
  running: "bg-indigo-100 text-indigo-700",
  completed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-stone-200 text-stone-500",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STYLES[status]}`}
    >
      {status === "running" && (
        <span className="mr-1.5 h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" />
      )}
      {status}
    </span>
  );
}
