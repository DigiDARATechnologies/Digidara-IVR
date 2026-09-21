import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface CrmConnection {
  configured: boolean;
  id?: number | null;
  provider: string;
  name?: string | null;
  endpoint_host?: string | null;
  is_active: boolean;
  field_mapping: Record<string, string>;
  last_tested_at?: string | null;
  last_test_status?: string | null;
  updated_at?: string | null;
}

export interface CrmEvent {
  id: number;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  status: string;
  attempts: number;
  max_attempts: number;
  available_at: string;
  delivered_at?: string | null;
  last_error?: string | null;
  response_status?: number | null;
  created_at: string;
  updated_at: string;
}

const crmKey = ["crm"] as const;

export const useCrmConnection = () => useQuery({
  queryKey: [...crmKey, "connection"],
  queryFn: async () => (await api.get<CrmConnection>("/crm/connection")).data,
});

export const useCrmEvents = () => useQuery({
  queryKey: [...crmKey, "events"],
  queryFn: async () => (await api.get<CrmEvent[]>("/crm/events")).data,
  refetchInterval: 15_000,
});

export function useSaveCrmConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; webhook_url: string; signing_secret: string; is_active: boolean; field_mapping: Record<string,string> }) =>
      (await api.put<CrmConnection>("/crm/connection", payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: crmKey }),
  });
}

export function useDisableCrmConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.delete("/crm/connection")).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: crmKey }),
  });
}

export function useTestCrmConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<{status:string;response_status:number}>("/crm/connection/test")).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: crmKey }),
  });
}

export function useRetryCrmEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => (await api.post(`/crm/events/${id}/retry`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: crmKey }),
  });
}
