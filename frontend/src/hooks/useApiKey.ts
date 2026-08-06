import { useCallback, useState } from "react";

const STORAGE_KEY = "research-agent:api-key";

/**
 * The backend authenticates with a single `X-API-Key` header, not user
 * accounts (see app/api/deps.py::get_current_api_key) -- so "auth" in this
 * UI is just persisting that key in localStorage, not a login flow.
 */
export function useApiKey() {
  const [apiKey, setApiKeyState] = useState<string>(() => localStorage.getItem(STORAGE_KEY) ?? "");

  const setApiKey = useCallback((key: string) => {
    localStorage.setItem(STORAGE_KEY, key);
    setApiKeyState(key);
  }, []);

  const clearApiKey = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setApiKeyState("");
  }, []);

  return { apiKey, setApiKey, clearApiKey, hasApiKey: apiKey.length > 0 };
}
