import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { CallTransfer, Department, StaffDestination } from "../types";

export function useDepartments(activeOnly = false) {
  return useQuery({
    queryKey: ["transfer-departments", activeOnly],
    queryFn: async () => (await api.get<Department[]>("/transfers/departments", {
      params: { active_only: activeOnly }
    })).data
  });
}

export function useCreateDepartment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: { name: string; description?: string; is_active?: boolean }) =>
      (await api.post<Department>("/transfers/departments", input)).data,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["transfer-departments"] });
      client.invalidateQueries({ queryKey: ["transfer-destinations"] });
    }
  });
}

export function useUpdateDepartment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, changes }: { id: number; changes: Partial<Department> }) =>
      (await api.patch<Department>(`/transfers/departments/${id}`, changes)).data,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["transfer-departments"] });
      client.invalidateQueries({ queryKey: ["transfer-destinations"] });
    }
  });
}

export function useDeleteDepartment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/transfers/departments/${id}`);
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["transfer-departments"] });
      client.invalidateQueries({ queryKey: ["transfer-destinations"] });
    }
  });
}

export function useTransferDestinations(activeOnly = false) {
  return useQuery({
    queryKey: ["transfer-destinations", activeOnly],
    queryFn: async () => (await api.get<StaffDestination[]>("/transfers/destinations", {
      params: { active_only: activeOnly }
    })).data
  });
}

export function useCreateTransferDestination() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: { name: string; phone_e164: string; department?: string; priority?: number }) =>
      (await api.post<StaffDestination>("/transfers/destinations", input)).data,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["transfer-destinations"] });
      client.invalidateQueries({ queryKey: ["transfer-departments"] });
    }
  });
}

export function useUpdateTransferDestination() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, changes }: { id: number; changes: Partial<StaffDestination> }) =>
      (await api.patch<StaffDestination>(`/transfers/destinations/${id}`, changes)).data,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["transfer-destinations"] });
      client.invalidateQueries({ queryKey: ["transfer-departments"] });
    }
  });
}

export function useDeleteTransferDestination() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/transfers/destinations/${id}`);
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["transfer-destinations"] });
      client.invalidateQueries({ queryKey: ["transfer-departments"] });
    }
  });
}

export function useCallTransfers(callId?: string | number) {
  return useQuery({
    queryKey: ["call-transfers", callId],
    queryFn: async () => (await api.get<CallTransfer[]>(`/transfers/calls/${callId}`)).data,
    enabled: Boolean(callId),
    refetchInterval: 3000
  });
}

export function useHumanTransfer(callId?: string | number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (target: number | { destinationId?: number; department?: string }) => {
      const payload = typeof target === "number"
        ? { destination_id: target }
        : { destination_id: target.destinationId, department: target.department };
      return (await api.post<CallTransfer>(
        `/transfers/calls/${callId}`,
        payload,
        { headers: { "Idempotency-Key": crypto.randomUUID() } }
      )).data;
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["call-transfers", callId] });
      client.invalidateQueries({ queryKey: ["calls", callId] });
    }
  });
}

