import { useJobsList } from "../hooks/useJobs";
import { formatRelativeTime } from "../lib/time";
import { StatusBadge } from "./StatusBadge";

interface SidebarProps {
  apiKey: string;
  selectedJobId: string | null;
  onSelectJob: (jobId: string) => void;
  onNewJob: () => void;
}

export function Sidebar({ apiKey, selectedJobId, onSelectJob, onNewJob }: SidebarProps) {
  const { data, isLoading, isError } = useJobsList(apiKey);

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-stone-200 bg-stone-100/60">
      <div className="p-3">
        <button
          onClick={onNewJob}
          className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-left text-sm font-medium text-stone-700 shadow-sm hover:bg-stone-50"
        >
          + New research
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3">
        {isLoading && <p className="px-2 py-4 text-sm text-stone-400">Loading history...</p>}
        {isError && (
          <p className="px-2 py-4 text-sm text-red-500">Couldn't load job history.</p>
        )}
        {data?.items.length === 0 && (
          <p className="px-2 py-4 text-sm text-stone-400">No research jobs yet.</p>
        )}
        <ul className="space-y-1">
          {data?.items.map((job) => (
            <li key={job.id}>
              <button
                onClick={() => onSelectJob(job.id)}
                className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${
                  job.id === selectedJobId ? "bg-white shadow-sm ring-1 ring-stone-200" : "hover:bg-stone-200/60"
                }`}
              >
                <p className="truncate text-sm text-stone-800">{job.query}</p>
                <div className="mt-1 flex items-center justify-between">
                  <StatusBadge status={job.status} />
                  <span className="text-xs text-stone-400">{formatRelativeTime(job.created_at)}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
