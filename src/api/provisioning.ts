import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

// Confirmed live against Plivo's India business Compliance API during
// integration testing — these two document types are what Plivo requires
// for an India "local" business number application.
export const REGISTRATION_DOCUMENT_TYPE_ID = "525a6b3a-2050-4556-8e2c-367cf30cd6ca";
export const GST_DOCUMENT_TYPE_ID = "8a048d56-d8cb-4148-a764-49f1326aa161";

// Trust-tier prefixes: chosen because 080/022-style numbers read as real
// landlines and get answered, not because of the customer's actual city.
// "160" is a known TRAI business-caller series but is left out until its
// exact Search API parameters are confirmed with Plivo.
export const NUMBER_PREFIXES = [
  { prefix: "080", city: "Bangalore" },
  { prefix: "022", city: "Mumbai" },
] as const;

export interface ProvisioningStatus {
  status: string;
  id?: number;
  plivo_compliance_id?: string | null;
  business_name?: string | null;
  provisioned_number?: string | null;
  subaccount_auth_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface AvailableNumber {
  number: string;
  city: string | null;
  region: string | null;
  monthly_rental_rate: string | null;
  voice_rate: string | null;
}

export interface ComplianceApplicationInput {
  business_name: string;
  business_email: string;
  address_line1: string;
  city: string;
  state: string;
  postal_code: string;
  registration_number: string;
  registrationCertificate: File;
  gstCertificate: File;
}

const statusKey = ["provisioning", "plivo", "status"] as const;

function isSettledStatus(status?: string): boolean {
  if (!status) return false;
  const normalized = status.toLowerCase();
  return normalized === "not_started" || normalized.includes("reject") || normalized.includes("accept") || normalized.includes("approv");
}

export function useProvisioningStatus() {
  return useQuery({
    queryKey: statusKey,
    queryFn: async () => (await api.get<ProvisioningStatus>("/provisioning/plivo/status")).data,
    refetchInterval: (query) => (isSettledStatus(query.state.data?.status) ? false : 5000),
  });
}

export function useSubmitCompliance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: ComplianceApplicationInput) => {
      const form = new FormData();
      form.append("business_name", input.business_name);
      form.append("business_email", input.business_email);
      form.append("address_line1", input.address_line1);
      form.append("city", input.city);
      form.append("state", input.state);
      form.append("postal_code", input.postal_code);
      form.append("registration_number", input.registration_number);
      form.append("document_type_ids", `${REGISTRATION_DOCUMENT_TYPE_ID},${GST_DOCUMENT_TYPE_ID}`);
      form.append("documents", input.registrationCertificate);
      form.append("documents", input.gstCertificate);
      const { data } = await api.post("/provisioning/plivo/compliance", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: statusKey }),
  });
}

export function useSearchNumbers(prefix: string | null) {
  return useQuery({
    queryKey: ["provisioning", "plivo", "numbers", prefix],
    queryFn: async () =>
      (await api.get<{ numbers: AvailableNumber[] }>("/provisioning/plivo/numbers", { params: { prefix } })).data
        .numbers,
    enabled: Boolean(prefix),
  });
}

export function useBuyNumber() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { number: string; complianceApplicationId: string }) => {
      const form = new FormData();
      form.append("number", input.number);
      form.append("compliance_application_id", input.complianceApplicationId);
      const { data } = await api.post("/provisioning/plivo/numbers/buy", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: statusKey }),
  });
}
