import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { PhoneNumber, PhoneNumberPayload, PhoneNumberUpdatePayload } from "../types";

export const phoneNumbersKey = ["phone-numbers"] as const;

export function usePhoneNumbers() {
  return useQuery({
    queryKey: phoneNumbersKey,
    queryFn: async () => {
      const { data } = await api.get<PhoneNumber[]>("/phone-numbers");
      return data;
    },
  });
}

export function useCreatePhoneNumber() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PhoneNumberPayload) => {
      const { data } = await api.post<PhoneNumber>("/phone-numbers", payload);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: phoneNumbersKey }),
  });
}

export function useUpdatePhoneNumber() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { id: number; payload: PhoneNumberUpdatePayload }) => {
      const { data } = await api.patch<PhoneNumber>(`/phone-numbers/${input.id}`, input.payload);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: phoneNumbersKey }),
  });
}

export function useDeletePhoneNumber() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/phone-numbers/${id}`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: phoneNumbersKey }),
  });
}
