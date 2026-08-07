import { useState } from "react";

import { ApiError } from "../api/client";
import type { LlmProvider } from "../api/types";
import { PROVIDER_LABELS } from "../api/types";
import { useApiKeysList, useCreateApiKey, useRevokeApiKey } from "../hooks/useApiKeys";
import { useAddCredential, useCredentialsList, useDeleteCredential } from "../hooks/useCredentials";
import { formatRelativeTime } from "../lib/time";

const PROVIDERS: LlmProvider[] = ["openai", "gemini", "anthropic"];

export function SettingsModal({ token, onClose }: { token: string; onClose: () => void }) {
  const [tab, setTab] = useState<"credentials" | "api-keys">("credentials");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-stone-200 px-5 py-3">
          <h2 className="text-sm font-semibold text-stone-900">Settings</h2>
          <button onClick={onClose} className="text-stone-400 hover:text-stone-600">
            ✕
          </button>
        </div>

        <div className="flex gap-1 border-b border-stone-200 px-5 pt-3">
          {(["credentials", "api-keys"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-t-lg px-3 py-1.5 text-xs font-medium ${
                tab === t
                  ? "border border-b-0 border-stone-200 bg-white text-stone-800"
                  : "text-stone-500 hover:text-stone-700"
              }`}
            >
              {t === "credentials" ? "LLM credentials" : "API keys"}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {tab === "credentials" ? <CredentialsSection token={token} /> : <ApiKeysSection token={token} />}
        </div>
      </div>
    </div>
  );
}

function CredentialsSection({ token }: { token: string }) {
  const { data: credentials, isLoading } = useCredentialsList(token);
  const addCredential = useAddCredential(token);
  const deleteCredential = useDeleteCredential(token);

  const [provider, setProvider] = useState<LlmProvider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [label, setLabel] = useState("");

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!apiKey.trim()) return;
    addCredential.mutate(
      { provider, api_key: apiKey.trim(), label: label.trim() || undefined },
      { onSuccess: () => setApiKey("") },
    );
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-stone-500">
        Bring your own API key for each provider you want to run research jobs on. Keys are encrypted
        at rest and are never shown again after they're added.
      </p>

      {isLoading && <p className="text-sm text-stone-400">Loading...</p>}
      {credentials && credentials.length > 0 && (
        <ul className="space-y-1.5">
          {credentials.map((credential) => (
            <li
              key={credential.id}
              className="flex items-center justify-between rounded-lg border border-stone-200 px-3 py-2 text-sm"
            >
              <div>
                <span className="font-medium text-stone-800">{PROVIDER_LABELS[credential.provider]}</span>
                {credential.label && <span className="ml-1.5 text-stone-400">({credential.label})</span>}
                <span
                  className={`ml-2 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                    credential.is_valid ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
                  }`}
                >
                  {credential.is_valid ? "valid" : "invalid"}
                </span>
                <p className="mt-0.5 text-xs text-stone-400">
                  added {formatRelativeTime(credential.created_at)}
                </p>
              </div>
              <button
                onClick={() => deleteCredential.mutate(credential.id)}
                disabled={deleteCredential.isPending}
                className="text-xs text-stone-500 underline hover:text-red-600"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={handleSubmit} className="space-y-2 border-t border-stone-100 pt-3">
        <div className="flex gap-2">
          <select
            value={provider}
            onChange={(event) => setProvider(event.target.value as LlmProvider)}
            className="rounded-lg border border-stone-300 px-2 py-1.5 text-sm"
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>
                {PROVIDER_LABELS[p]}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="Label (optional)"
            className="flex-1 rounded-lg border border-stone-300 px-2 py-1.5 text-sm"
          />
        </div>
        <input
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="API key"
          className="w-full rounded-lg border border-stone-300 px-3 py-1.5 text-sm"
        />
        <button
          type="submit"
          disabled={!apiKey.trim() || addCredential.isPending}
          className="w-full rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {addCredential.isPending ? "Validating..." : "Add credential"}
        </button>
        {addCredential.isError && (
          <p className="text-xs text-red-500">
            {addCredential.error instanceof ApiError
              ? addCredential.error.message
              : "Failed to add credential."}
          </p>
        )}
      </form>
    </div>
  );
}

function ApiKeysSection({ token }: { token: string }) {
  const { data: apiKeys, isLoading } = useApiKeysList(token);
  const createApiKey = useCreateApiKey(token);
  const revokeApiKey = useRevokeApiKey(token);

  const [name, setName] = useState("");
  const [justCreatedRawKey, setJustCreatedRawKey] = useState<string | null>(null);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    createApiKey.mutate(
      { name: name.trim() },
      {
        onSuccess: (response) => {
          setName("");
          setJustCreatedRawKey(response.raw_key);
        },
      },
    );
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-stone-500">
        Developer API keys authenticate scripts/programmatic access to this platform's own API (the{" "}
        <code className="rounded bg-stone-100 px-1 py-0.5">X-API-Key</code> header) -- separate from
        your LLM provider credentials above.
      </p>

      {justCreatedRawKey && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800">
          <p className="font-medium">Copy this key now -- it won't be shown again.</p>
          <code className="mt-1 block break-all rounded bg-white px-2 py-1">{justCreatedRawKey}</code>
        </div>
      )}

      {isLoading && <p className="text-sm text-stone-400">Loading...</p>}
      {apiKeys && apiKeys.length > 0 && (
        <ul className="space-y-1.5">
          {apiKeys.map((key) => (
            <li
              key={key.id}
              className="flex items-center justify-between rounded-lg border border-stone-200 px-3 py-2 text-sm"
            >
              <div>
                <span className="font-medium text-stone-800">{key.name}</span>
                {!key.is_active && <span className="ml-2 text-xs text-stone-400">(revoked)</span>}
                <p className="mt-0.5 text-xs text-stone-400">created {formatRelativeTime(key.created_at)}</p>
              </div>
              {key.is_active && (
                <button
                  onClick={() => revokeApiKey.mutate(key.id)}
                  disabled={revokeApiKey.isPending}
                  className="text-xs text-stone-500 underline hover:text-red-600"
                >
                  Revoke
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-stone-100 pt-3">
        <input
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Key name, e.g. 'CI script'"
          className="flex-1 rounded-lg border border-stone-300 px-3 py-1.5 text-sm"
        />
        <button
          type="submit"
          disabled={!name.trim() || createApiKey.isPending}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Create
        </button>
      </form>
    </div>
  );
}
