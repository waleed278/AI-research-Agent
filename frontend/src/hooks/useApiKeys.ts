import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createApiKey, listApiKeys, revokeApiKey } from "../api/client";
import type { CreateApiKeyRequest } from "../api/types";

const API_KEYS_KEY = ["api-keys"] as const;

export function useApiKeysList(token: string) {
  return useQuery({
    queryKey: API_KEYS_KEY,
    queryFn: () => listApiKeys(token),
    enabled: token.length > 0,
  });
}

export function useCreateApiKey(token: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateApiKeyRequest) => createApiKey(token, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: API_KEYS_KEY });
    },
  });
}

export function useRevokeApiKey(token: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => revokeApiKey(token, keyId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: API_KEYS_KEY });
    },
  });
}
