import { useState } from "react";

import { ApiError } from "../api/client";
import { useCreateJob } from "../hooks/useJobs";

interface NewJobFormProps {
  apiKey: string;
  onCreated: (jobId: string) => void;
}

export function NewJobForm({ apiKey, onCreated }: NewJobFormProps) {
  const [query, setQuery] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [maxIterations, setMaxIterations] = useState<number | "">("");
  const [maxSources, setMaxSources] = useState<number | "">("");
  const createJob = useCreateJob(apiKey);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (query.trim().length < 8) return;

    createJob.mutate(
      {
        query: query.trim(),
        max_iterations: maxIterations === "" ? undefined : maxIterations,
        max_sources: maxSources === "" ? undefined : maxSources,
      },
      {
        onSuccess: (response) => {
          setQuery("");
          onCreated(response.id);
        },
      },
    );
  };

  return (
    <form onSubmit={handleSubmit} className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm">
      <textarea
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Ask a research question, e.g. What are the main causes of the 2008 financial crisis?"
        rows={2}
        className="w-full resize-none border-none text-sm text-stone-800 placeholder:text-stone-400 focus:outline-none"
      />

      <div className="mt-2 flex items-center justify-between">
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-xs text-stone-500 hover:text-stone-700"
        >
          {showAdvanced ? "Hide" : "Advanced"} options
        </button>
        <button
          type="submit"
          disabled={query.trim().length < 8 || createJob.isPending}
          className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {createJob.isPending ? "Starting..." : "Research"}
        </button>
      </div>

      {showAdvanced && (
        <div className="mt-3 grid grid-cols-2 gap-3 border-t border-stone-100 pt-3">
          <label className="text-xs text-stone-500">
            Max tool-call steps
            <input
              type="number"
              min={1}
              max={20}
              value={maxIterations}
              onChange={(event) =>
                setMaxIterations(event.target.value === "" ? "" : Number(event.target.value))
              }
              placeholder="default"
              className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
          </label>
          <label className="text-xs text-stone-500">
            Max sources
            <input
              type="number"
              min={1}
              max={20}
              value={maxSources}
              onChange={(event) =>
                setMaxSources(event.target.value === "" ? "" : Number(event.target.value))
              }
              placeholder="default"
              className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
          </label>
        </div>
      )}

      {createJob.isError && (
        <p className="mt-2 text-xs text-red-500">
          {createJob.error instanceof ApiError
            ? createJob.error.message
            : "Failed to start the research job."}
        </p>
      )}
    </form>
  );
}
