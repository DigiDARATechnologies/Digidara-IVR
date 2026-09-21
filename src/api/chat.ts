import { api } from "./client";
import type { ChatResponse } from "../types";

export async function sendChatMessage(input: {
  campaignId: number;
  customerId?: number;
  message: string;
}): Promise<ChatResponse> {
  const path = input.customerId
    ? `/ai/chat/${input.campaignId}/${input.customerId}`
    : `/ai/chat/${input.campaignId}`;
  const { data } = await api.post<ChatResponse>(path, { message: input.message });
  return data;
}
