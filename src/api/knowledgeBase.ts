import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { KBDocument, KBStatus } from "../types";

const KB_KEY = ["knowledge-base"];

export function useKBStatus(enabled: boolean = true) {
  return useQuery<KBStatus>({
    queryKey: [...KB_KEY, "status"],
    queryFn: async () => {
      const { data } = await api.get("/knowledge-base/status");
      return data;
    },
    enabled,
    refetchInterval: (q) => (enabled && !q.state.data?.available ? 10000 : false),
  });
}

export function useKBDocuments(collection: string, enabled: boolean = true) {
  return useQuery<KBDocument[]>({
    queryKey: [...KB_KEY, "docs", collection],
    queryFn: async () => {
      const { data } = await api.get(`/knowledge-base/collections/${collection}/documents`);
      return data;
    },
    enabled: enabled && Boolean(collection),
  });
}

export function useAddDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      collection: string;
      doc_id: string;
      text: string;
      source?: string;
    }) => {
      const { data } = await api.post("/knowledge-base/documents", payload);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KB_KEY }),
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ collection, doc_id }: { collection: string; doc_id: string }) => {
      const { data } = await api.delete(`/knowledge-base/collections/${collection}/documents/${doc_id}`);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KB_KEY }),
  });
}

export function useKBSearch(query: string, collection?: string) {
  return useQuery({
    queryKey: [...KB_KEY, "search", query, collection],
    queryFn: async () => {
      const params = new URLSearchParams({ query, top_k: "5" });
      if (collection) params.append("collection", collection);
      const { data } = await api.get(`/knowledge-base/search?${params}`);
      return data;
    },
    enabled: query.length > 3,
  });
}

export function useLeadQualifications(customerId?: number) {
  return useQuery({
    queryKey: ["lead-qualifications", customerId],
    queryFn: async () => {
      const params = customerId ? `?customer_id=${customerId}` : "";
      const { data } = await api.get(`/lead-qualifications${params}`);
      return data;
    },
  });
}

export function useCustomerMemory(customerId?: number) {
  return useQuery({
    queryKey: ["customer-memory", customerId],
    queryFn: async () => {
      const { data } = await api.get(`/customer-memory/${customerId}`);
      return data;
    },
    enabled: Boolean(customerId),
  });
}
