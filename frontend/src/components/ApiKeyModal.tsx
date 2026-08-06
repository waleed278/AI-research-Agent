import { useState } from "react";

interface ApiKeyModalProps {
  currentKey: string;
  onSave: (key: string) => void;
  onClose: () => void;
}

export function ApiKeyModal({ currentKey, onSave, onClose }: ApiKeyModalProps) {
  const [value, setValue] = useState(currentKey);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-stone-900">API key</h2>
        <p className="mt-1 text-sm text-stone-500">
          The backend authenticates requests with an API key (the{" "}
          <code className="rounded bg-stone-100 px-1 py-0.5">X-API-Key</code> header) rather than
          user accounts. For local development, seed and use the default key:{" "}
          <code className="rounded bg-stone-100 px-1 py-0.5">dev-local-key</code>.
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            onSave(value.trim());
          }}
        >
          <input
            autoFocus
            type="text"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="dev-local-key"
            className="mt-4 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={value.trim().length === 0}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
