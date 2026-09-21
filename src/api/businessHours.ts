import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface DaySchedule {
  day_of_week: number; // 0=Monday .. 6=Sunday
  is_closed: boolean;
  open_time: string | null; // "HH:MM", organization-local time
  close_time: string | null;
}

export interface BusinessHours {
  organization_id: number;
  timezone: string;
  configured: boolean;
  days: DaySchedule[];
}

export interface BusinessHoursStatus {
  is_open: boolean;
  configured: boolean;
  organization_timezone: string;
  local_time: string;
  day_of_week: number;
}

export const businessHoursKey = ["business-hours"] as const;
export const businessHoursStatusKey = ["business-hours", "status"] as const;

export function useBusinessHours() {
  return useQuery({
    queryKey: businessHoursKey,
    queryFn: async () => (await api.get<BusinessHours>("/business-hours")).data,
  });
}

export function useBusinessHoursStatus() {
  return useQuery({
    queryKey: businessHoursStatusKey,
    queryFn: async () => (await api.get<BusinessHoursStatus>("/business-hours/status")).data,
    refetchInterval: 60_000,
  });
}

export function useSaveBusinessHours() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { timezone: string; days: DaySchedule[] }) => {
      const { data } = await api.put<BusinessHours>("/business-hours", input);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: businessHoursKey });
      queryClient.invalidateQueries({ queryKey: businessHoursStatusKey });
    },
  });
}
