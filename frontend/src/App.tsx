import { useState } from "react";

import { AuthScreen } from "./components/AuthScreen";
import { JobView } from "./components/JobView";
import { NewJobForm } from "./components/NewJobForm";
import { SettingsModal } from "./components/SettingsModal";
import { Sidebar } from "./components/Sidebar";
import { useAuth } from "./hooks/useAuth";

export default function App() {
  const auth = useAuth();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  if (!auth.isAuthenticated) {
    return <AuthScreen auth={auth} />;
  }

  const token = auth.token as string;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex shrink-0 items-center justify-between border-b border-stone-200 bg-white px-4 py-3">
        <h1 className="text-sm font-semibold tracking-tight text-stone-800">🔎 Research Agent</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-stone-400">{auth.user?.email}</span>
          <button
            onClick={() => setShowSettings(true)}
            className="rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100"
          >
            Settings
          </button>
          <button
            onClick={auth.logout}
            className="rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100"
          >
            Log out
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <Sidebar
          token={token}
          selectedJobId={selectedJobId}
          onSelectJob={setSelectedJobId}
          onNewJob={() => setSelectedJobId(null)}
        />

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-4 p-6">
            <NewJobForm
              token={token}
              onCreated={setSelectedJobId}
              onOpenSettings={() => setShowSettings(true)}
            />

            {selectedJobId ? (
              <JobView token={token} jobId={selectedJobId} />
            ) : (
              <div className="pt-8 text-center text-sm text-stone-400">
                Ask a research question above, or pick a past job from the sidebar.
              </div>
            )}
          </div>
        </main>
      </div>

      {showSettings && <SettingsModal token={token} onClose={() => setShowSettings(false)} />}
    </div>
  );
}
