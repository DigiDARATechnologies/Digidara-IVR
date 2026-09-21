import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface CredentialStatus {
  provider: string;
  configured: boolean;
  last_four: string | null;
  rotated_at: string | null;
}

const credentialsKey = ["integrations", "credentials"] as const;

export function useCredentialStatus() {
  return useQuery({
    queryKey: credentialsKey,
    queryFn: async () => (await api.get<CredentialStatus[]>("/integrations/credentials")).data,
  });
}

export function useSaveCredential() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ provider, fields }: { provider: string; fields: Record<string, string> }) =>
      (await api.put(`/integrations/credentials/${provider}`, { fields })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: credentialsKey }),
  });
}

export function useRemoveCredential() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (provider: string) => (await api.delete(`/integrations/credentials/${provider}`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: credentialsKey }),
  });
}
