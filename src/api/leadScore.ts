import { useMutation } from "@tanstack/react-query";
import { api } from "./client";
import type { LeadScoreRequest, LeadScoreResponse } from "../types";

export function useLeadScore() {
  return useMutation({
    mutationFn: async (payload: LeadScoreRequest) => {
      const { data } = await api.post<LeadScoreResponse>("/lead-score/preview", payload);
      return data;
    }
  });
}
