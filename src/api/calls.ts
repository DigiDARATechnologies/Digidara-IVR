import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { CallLog, RunSheetRequest, RunSheetResult, SheetStatusResult, StartCallResponse } from "../types";

export const callsKey = ["calls"] as const;

export function useCallLogs(refetchInterval?: number | false) {
  return useQuery({
    queryKey: callsKey,
    queryFn: async () => {
      const { data } = await api.get<CallLog[]>("/calls/logs");
      return data;
    },
    refetchInterval
  });
}

export function useCallLog(id?: string | number) {
  return useQuery({
    queryKey: ["calls", id],
    queryFn: async () => (await api.get<CallLog>(`/calls/logs/${id}`)).data,
    enabled: Boolean(id)
  });
}

export async function getRecordingUrl(id: number): Promise<string> {
  const { data } = await api.get<Blob>(`/calls/logs/${id}/recording?enhanced=true`, { responseType: "blob" });
  return URL.createObjectURL(data);
}

export function useTerminateCall() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number | string) => {
      const { data } = await api.post(`/calls/logs/${id}/terminate`);
      return data;
    },
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: callsKey });
      queryClient.invalidateQueries({ queryKey: ["calls", id] });
    }
  });
}

export function useStartCall() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { customerId: number; campaignId: number }) => {
      const { data } = await api.post<StartCallResponse>(
        `/calls/start/${input.customerId}/${input.campaignId}`
      );
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: callsKey })
  });
}

export function useRunSheet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: RunSheetRequest) => {
      const { data } = await api.post<RunSheetResult>("/calls/run-sheet", payload);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: callsKey })
  });
}

export function useRunUpload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { file: File; campaignId: number }) => {
      const form = new FormData();
      form.append("file", input.file);
      form.append("campaign_id", String(input.campaignId));
      const { data } = await api.post<RunSheetResult>(
        "/calls/run-upload",
        form,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: callsKey })
  });
}

export function useSheetStatus(sheetUrl: string, enabled: boolean) {
  return useQuery({
    queryKey: ["sheet-status", sheetUrl],
    queryFn: async () => {
      const { data } = await api.get<SheetStatusResult>("/calls/sheet-status", {
        params: { sheet_url: sheetUrl }
      });
      return data;
    },
    enabled,
    refetchInterval: enabled ? 4000 : false
  });
}
