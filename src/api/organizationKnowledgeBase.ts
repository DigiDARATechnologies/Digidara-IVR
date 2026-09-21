import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface OrgKBDocument {
  doc_id: string;
  lang: string;
  collection: string;
  chunk_count: number;
  updated_at: string | null;
}

export interface AddOrgDocumentInput {
  collection: string;
  doc_id: string;
  text: string;
  lang: string;
  file?: File | null;
}

const ORG_KB_KEY = ["organization-knowledge-base", "documents"] as const;

export function useOrgKBDocuments() {
  return useQuery({
    queryKey: ORG_KB_KEY,
    queryFn: async () => (await api.get<OrgKBDocument[]>("/organization-knowledge-base/documents")).data,
  });
}

export function useAddOrgDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: AddOrgDocumentInput) => {
      const form = new FormData();
      form.append("collection", payload.collection);
      form.append("doc_id", payload.doc_id);
      form.append("lang", payload.lang);
      form.append("text", payload.text);
      if (payload.file) form.append("file", payload.file);
      const { data } = await api.post("/organization-knowledge-base/documents", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ORG_KB_KEY }),
  });
}

export function useDeleteOrgDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (docId: string) =>
      (await api.delete(`/organization-knowledge-base/documents/${encodeURIComponent(docId)}`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ORG_KB_KEY }),
  });
}
