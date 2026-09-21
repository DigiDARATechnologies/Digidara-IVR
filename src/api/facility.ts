import { api } from "./client";

export interface FacilityAgentResponse {
  reply: string;
  route: string;
  route_source: string;
  citations: Array<{ source_id: string; title: string; document_type: string; revision: string }>;
  requires_confirmation: boolean;
}

export async function queryFacilityAgent(message: string): Promise<FacilityAgentResponse> {
  const response = await api.post<FacilityAgentResponse>("/facility/agent/query", { message });
  return response.data;
}

export async function seedFacilityDemo() {
  const response = await api.post("/facility/demo/seed");
  return response.data;
}
