import { useJobEvents } from "../hooks/useJobEvents";
import { useCancelJob, useJob } from "../hooks/useJobs";
import { ProgressPanel } from "./ProgressPanel";
import { ReportView } from "./ReportView";
import { StatusBadge } from "./StatusBadge";

export function JobView({ apiKey, jobId }: { apiKey: string; jobId: string }) {
  const { data: job, isLoading, isError } = useJob(apiKey, jobId);
  const cancelJob = useCancelJob(apiKey);
  const isRunning = job?.status === "queued" || job?.status === "running";
  const events = useJobEvents(apiKey, jobId, isRunning);

  if (isLoading) {
    return <p className="text-sm text-stone-400">Loading job...</p>;
  }
  if (isError || !job) {
    return <p className="text-sm text-red-500">Couldn't load this job.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <h1 className="text-lg font-medium text-stone-900">{job.query}</h1>
        <div className="flex shrink-0 items-center gap-3">
          <StatusBadge status={job.status} />
          {job.status === "queued" && (
            <button
              onClick={() => cancelJob.mutate(job.id)}
              disabled={cancelJob.isPending}
              className="text-xs text-stone-500 underline hover:text-stone-700"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {job.total_tokens > 0 && (
        <p className="text-xs text-stone-400">
          {job.total_tokens.toLocaleString()} tokens · ${job.total_cost_usd.toFixed(4)}
        </p>
      )}

      {isRunning && <ProgressPanel phase={job.phase} events={events} />}

      {job.status === "completed" && job.result && <ReportView result={job.result} />}

      {job.status === "failed" && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p className="font-medium">This research job failed.</p>
          {job.error && <p className="mt-1 whitespace-pre-wrap text-xs">{job.error}</p>}
        </div>
      )}

      {job.status === "cancelled" && (
        <div className="rounded-xl border border-stone-200 bg-stone-50 p-4 text-sm text-stone-600">
          This job was cancelled before it started.
        </div>
      )}
    </div>
  );
}
