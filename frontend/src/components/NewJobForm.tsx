import { useState } from "react";

import { ApiError } from "../api/client";
import type { LlmProvider } from "../api/types";
import { DEFAULT_MODEL_BY_PROVIDER, PROVIDER_LABELS, SUPPORTED_MODELS } from "../api/types";
import { useCredentialsList } from "../hooks/useCredentials";
import { useCreateJob } from "../hooks/useJobs";
import { useUploadFile } from "../hooks/useUploads";

interface NewJobFormProps {
  token: string;
  onCreated: (jobId: string) => void;
  onOpenSettings: () => void;
}

interface AttachedFile {
  id: string;
  filename: string;
}

export function NewJobForm({ token, onCreated, onOpenSettings }: NewJobFormProps) {
  const { data: credentials, isLoading: credentialsLoading } = useCredentialsList(token);
  const availableProviders = (credentials ?? [])
    .filter((c) => c.is_valid)
    .map((c) => c.provider);

  const [query, setQuery] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [maxIterations, setMaxIterations] = useState<number | "">("");
  const [maxSources, setMaxSources] = useState<number | "">("");
  const [provider, setProvider] = useState<LlmProvider | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<AttachedFile[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const createJob = useCreateJob(token);
  const uploadFile = useUploadFile(token);

  const activeProvider = provider && availableProviders.includes(provider) ? provider : availableProviders[0];
  const activeModel = model ?? (activeProvider ? DEFAULT_MODEL_BY_PROVIDER[activeProvider] : undefined);

  if (credentialsLoading) {
    return <p className="text-sm text-stone-400">Loading...</p>;
  }

  if (availableProviders.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-stone-300 p-6 text-center text-sm text-stone-500">
        Add an LLM provider credential to start a research job.
        <button
          onClick={onOpenSettings}
          className="mt-2 block w-full text-indigo-600 underline hover:text-indigo-800"
        >
          Open Settings
        </button>
      </div>
    );
  }

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    setUploadError(null);

    for (const file of files) {
      uploadFile.mutate(file, {
        onSuccess: (response) => {
          setAttachments((prev) => [...prev, { id: response.id, filename: response.filename }]);
        },
        onError: (error) => {
          setUploadError(error instanceof ApiError ? error.message : `Failed to upload ${file.name}.`);
        },
      });
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (query.trim().length < 8 || !activeProvider) return;

    createJob.mutate(
      {
        query: query.trim(),
        provider: activeProvider,
        model: activeModel,
        max_iterations: maxIterations === "" ? undefined : maxIterations,
        max_sources: maxSources === "" ? undefined : maxSources,
        attachment_ids: attachments.map((a) => a.id),
      },
      {
        onSuccess: (response) => {
          setQuery("");
          setAttachments([]);
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

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select
          value={activeProvider}
          onChange={(event) => {
            setProvider(event.target.value as LlmProvider);
            setModel(null);
          }}
          className="rounded-md border border-stone-300 px-2 py-1 text-xs"
        >
          {availableProviders.map((p) => (
            <option key={p} value={p}>
              {PROVIDER_LABELS[p]}
            </option>
          ))}
        </select>
        {activeProvider && (
          <select
            value={activeModel}
            onChange={(event) => setModel(event.target.value)}
            className="rounded-md border border-stone-300 px-2 py-1 text-xs"
          >
            {SUPPORTED_MODELS[activeProvider].map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        )}
        <label className="cursor-pointer rounded-md border border-dashed border-stone-300 px-2 py-1 text-xs text-stone-500 hover:bg-stone-50">
          + Attach file
          <input
            type="file"
            multiple
            accept=".txt,.md,.csv,.pdf"
            onChange={handleFilesSelected}
            className="hidden"
          />
        </label>
      </div>

      {attachments.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {attachments.map((file) => (
            <li
              key={file.id}
              className="flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-600"
            >
              {file.filename}
              <button
                type="button"
                onClick={() => setAttachments((prev) => prev.filter((f) => f.id !== file.id))}
                className="text-stone-400 hover:text-red-500"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      {uploadError && <p className="mt-1 text-xs text-red-500">{uploadError}</p>}

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
