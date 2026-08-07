import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { ApiError, getMe, login as loginRequest, signup as signupRequest } from "../api/client";
import type { LoginRequest, SignupRequest, UserResponse } from "../api/types";

const STORAGE_KEY = "research-agent:token";
const ME_KEY = ["auth", "me"] as const;

/**
 * Holds the JWT issued by `/auth/login` or `/auth/signup` (see
 * app/core/jwt.py) and the current user. The token is persisted in
 * localStorage so a refresh doesn't log the user out; `GET /auth/me` is
 * used both to restore the user on load and as an ongoing validity check --
 * a token that's expired or been invalidated server-side (user deactivated)
 * surfaces as a 401 here and triggers an automatic logout, the same
 * "poll for ground truth" pattern `useJob` uses for job status.
 */
export function useAuth() {
  const [token, setTokenState] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY));
  const queryClient = useQueryClient();

  const meQuery = useQuery({
    queryKey: ME_KEY,
    queryFn: () => getMe(token as string),
    enabled: token !== null,
    retry: false,
  });

  const setSession = useCallback(
    (newToken: string, user: UserResponse) => {
      localStorage.setItem(STORAGE_KEY, newToken);
      setTokenState(newToken);
      queryClient.setQueryData(ME_KEY, user);
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setTokenState(null);
    queryClient.setQueryData(ME_KEY, undefined);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    if (token && meQuery.error instanceof ApiError && meQuery.error.status === 401) {
      logout();
    }
  }, [token, meQuery.error, logout]);

  const signupMutation = useMutation({
    mutationFn: (body: SignupRequest) => signupRequest(body),
    onSuccess: (response) => setSession(response.access_token, response.user),
  });

  const loginMutation = useMutation({
    mutationFn: (body: LoginRequest) => loginRequest(body),
    onSuccess: (response) => setSession(response.access_token, response.user),
  });

  return {
    token,
    user: meQuery.data ?? null,
    isAuthenticated: token !== null && meQuery.data !== undefined,
    isLoading: token !== null && meQuery.isLoading,
    signup: signupMutation,
    login: loginMutation,
    logout,
  };
}
