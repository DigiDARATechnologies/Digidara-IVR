import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Customer, CustomerPayload } from "../types";

export const customersKey = ["customers"] as const;

export function useCustomers() {
  return useQuery({
    queryKey: customersKey,
    queryFn: async () => {
      const { data } = await api.get<Customer[]>("/customers");
      return data;
    }
  });
}

export function useSaveCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { id?: number; payload: CustomerPayload }) => {
      const { data } = input.id
        ? await api.put<Customer>(`/customers/${input.id}`, input.payload)
        : await api.post<Customer>("/customers", input.payload);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: customersKey })
  });
}

export function useDeleteCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/customers/${id}`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: customersKey })
  });
}
