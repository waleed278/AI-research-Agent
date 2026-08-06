import { useState } from "react";

import { ApiKeyModal } from "./components/ApiKeyModal";
import { JobView } from "./components/JobView";
import { NewJobForm } from "./components/NewJobForm";
import { Sidebar } from "./components/Sidebar";
import { useApiKey } from "./hooks/useApiKey";

export default function App() {
  const { apiKey, setApiKey, hasApiKey } = useApiKey();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [showApiKeyModal, setShowApiKeyModal] = useState(!hasApiKey);

  return (
    <div className="flex h-screen flex-col">
      <header className="flex shrink-0 items-center justify-between border-b border-stone-200 bg-white px-4 py-3">
        <h1 className="text-sm font-semibold tracking-tight text-stone-800">🔎 Research Agent</h1>
        <button
          onClick={() => setShowApiKeyModal(true)}
          className="rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100"
        >
          {hasApiKey ? "API key set" : "Set API key"}
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        <Sidebar
          apiKey={apiKey}
          selectedJobId={selectedJobId}
          onSelectJob={setSelectedJobId}
          onNewJob={() => setSelectedJobId(null)}
        />

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-4 p-6">
            {hasApiKey ? (
              <NewJobForm apiKey={apiKey} onCreated={setSelectedJobId} />
            ) : (
              <div className="rounded-xl border border-dashed border-stone-300 p-6 text-center text-sm text-stone-500">
                Set an API key to start a research job.
              </div>
            )}

            {selectedJobId && hasApiKey ? (
              <JobView apiKey={apiKey} jobId={selectedJobId} />
            ) : (
              hasApiKey && (
                <div className="pt-8 text-center text-sm text-stone-400">
                  Ask a research question above, or pick a past job from the sidebar.
                </div>
              )
            )}
          </div>
        </main>
      </div>

      {showApiKeyModal && (
        <ApiKeyModal
          currentKey={apiKey}
          onSave={(key) => {
            setApiKey(key);
            setShowApiKeyModal(false);
          }}
          onClose={() => setShowApiKeyModal(false)}
        />
      )}
    </div>
  );
}
