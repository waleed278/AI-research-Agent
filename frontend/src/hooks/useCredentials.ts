import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { addCredential, deleteCredential, listCredentials } from "../api/client";
import type { AddLlmCredentialRequest } from "../api/types";

const CREDENTIALS_KEY = ["credentials"] as const;

export function useCredentialsList(token: string) {
  return useQuery({
    queryKey: CREDENTIALS_KEY,
    queryFn: () => listCredentials(token),
    enabled: token.length > 0,
  });
}

export function useAddCredential(token: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AddLlmCredentialRequest) => addCredential(token, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CREDENTIALS_KEY });
    },
  });
}

export function useDeleteCredential(token: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentialId: string) => deleteCredential(token, credentialId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CREDENTIALS_KEY });
    },
  });
}
