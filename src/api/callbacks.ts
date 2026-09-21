import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CallbackStatus, CallbackSummary, CallbackTask, CallbackUpdate } from "../types";
import { api } from "./client";

export const callbacksKey = ["callbacks"] as const;

export function useCallbacks(filters: { status?: CallbackStatus | ""; search?: string }) {
  return useQuery({
    queryKey: [...callbacksKey, filters.status || "all", filters.search || ""],
    queryFn: async () => (await api.get<CallbackTask[]>("/callbacks", {
      params: { status: filters.status || undefined, search: filters.search || undefined },
    })).data,
    refetchInterval: 30_000,
  });
}

export function useCallbackSummary() {
  return useQuery({
    queryKey: [...callbacksKey, "summary"],
    queryFn: async () => (await api.get<CallbackSummary>("/callbacks/summary")).data,
    refetchInterval: 30_000,
  });
}

export function useUpdateCallback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, update }: { id: number; update: CallbackUpdate }) =>
      (await api.patch<CallbackTask>(`/callbacks/${id}`, update)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: callbacksKey }),
  });
}

