import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { IvrSettings } from "../types";

export const ivrSettingsKey = ["ivr-settings"] as const;

export function useIvrSettings() {
  return useQuery({ queryKey: ivrSettingsKey, queryFn: async () => (await api.get<IvrSettings>("/ivr/settings")).data });
}

export function useSaveIvrSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (value: IvrSettings) => (await api.put<IvrSettings>("/ivr/settings", value)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ivrSettingsKey }),
  });
}
