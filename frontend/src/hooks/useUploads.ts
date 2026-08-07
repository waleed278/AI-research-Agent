import { useMutation } from "@tanstack/react-query";

import { uploadFile } from "../api/client";

export function useUploadFile(token: string) {
  return useMutation({
    mutationFn: (file: File) => uploadFile(token, file),
  });
}
