import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Campaign, CampaignPayload } from "../types";

export const campaignsKey = ["campaigns"] as const;

export function useCampaigns() {
  return useQuery({
    queryKey: campaignsKey,
    queryFn: async () => {
      const { data } = await api.get<Campaign[]>("/campaigns");
      return data;
    }
  });
}

export function useSaveCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { id?: number; payload: CampaignPayload }) => {
      const { data } = input.id
        ? await api.put<Campaign>(`/campaigns/${input.id}`, input.payload)
        : await api.post<Campaign>("/campaigns", input.payload);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: campaignsKey, refetchType: "all" })
  });
}

export function useDeleteCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/campaigns/${id}`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: campaignsKey })
  });
}
