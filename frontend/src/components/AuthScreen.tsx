import { useState } from "react";

import { ApiError } from "../api/client";
import type { useAuth } from "../hooks/useAuth";

type Mode = "login" | "signup";

export function AuthScreen({ auth }: { auth: ReturnType<typeof useAuth> }) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const mutation = mode === "login" ? auth.login : auth.signup;
  const passwordTooShort = mode === "signup" && password.length > 0 && password.length < 8;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!email || !password || passwordTooShort) return;
    mutation.mutate({ email, password });
  };

  return (
    <div className="flex h-screen items-center justify-center bg-stone-50 px-4">
      <div className="w-full max-w-sm rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
        <h1 className="text-center text-sm font-semibold tracking-tight text-stone-800">
          🔎 Research Agent
        </h1>
        <p className="mt-1 text-center text-xs text-stone-500">
          {mode === "login" ? "Log in to continue." : "Create an account to get started."}
        </p>

        <form onSubmit={handleSubmit} className="mt-5 space-y-3">
          <label className="block text-xs text-stone-500">
            Email
            <input
              autoFocus
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </label>
          <label className="block text-xs text-stone-500">
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            {passwordTooShort && (
              <span className="mt-1 block text-xs text-red-500">
                Password must be at least 8 characters.
              </span>
            )}
          </label>

          <button
            type="submit"
            disabled={!email || !password || passwordTooShort || mutation.isPending}
            className="w-full rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {mutation.isPending
              ? mode === "login"
                ? "Logging in..."
                : "Signing up..."
              : mode === "login"
                ? "Log in"
                : "Sign up"}
          </button>

          {mutation.isError && (
            <p className="text-xs text-red-500">
              {mutation.error instanceof ApiError
                ? mutation.error.message
                : mode === "login"
                  ? "Failed to log in."
                  : "Failed to sign up."}
            </p>
          )}
        </form>

        <button
          type="button"
          onClick={() => setMode(mode === "login" ? "signup" : "login")}
          className="mt-4 w-full text-center text-xs text-stone-500 hover:text-stone-700"
        >
          {mode === "login" ? "Need an account? Sign up" : "Already have an account? Log in"}
        </button>
      </div>
    </div>
  );
}
