import type { CallLog, Customer } from "../types";

export type LeadTier = "hot" | "warm" | "cold" | "unscored";

export interface DerivedLead {
  customer: Customer;
  latestCall: CallLog | null;
  callCount: number;
  leadScore: number | null;
  leadStatus: string | null;
  tier: LeadTier;
  lastContacted: string | null;
}

/**
 * Classifies a lead into hot/warm/cold/unscored using the AI-derived
 * lead_score (0-100) and lead_status string from the customer's most
 * recent call log. No new database table required — this is computed
 * client-side from existing customers + call_logs data.
 */
export function tierFromScore(score: number | null, status: string | null): LeadTier {
  if (score === null || score === undefined) {
    // Fall back to status-only classification if no numeric score exists yet.
    if (status === "interested") return "warm";
    if (status === "not_interested" || status === "no_answer") return "cold";
    return "unscored";
  }
  if (score >= 70) return "hot";
  if (score >= 40) return "warm";
  return "cold";
}

export function buildLeads(customers: Customer[], callLogs: CallLog[]): DerivedLead[] {
  const callsByCustomer = new Map<number, CallLog[]>();
  callLogs.forEach((log) => {
    if (!log.customer_id) return;
    const list = callsByCustomer.get(log.customer_id) || [];
    list.push(log);
    callsByCustomer.set(log.customer_id, list);
  });

  return customers.map((customer) => {
    const calls = (callsByCustomer.get(customer.id) || []).sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at.replace(" ", "T")).getTime() : 0;
      const tb = b.created_at ? new Date(b.created_at.replace(" ", "T")).getTime() : 0;
      return tb - ta;
    });
    const latestCall = calls[0] || null;
    const leadScore = latestCall?.lead_score ?? null;
    const leadStatus = latestCall?.lead_status ?? null;

    // Prefer the qualification column (stored by finalize_call_log),
    // fall back to computing from lead_score if not available yet.
    let tier: LeadTier = "unscored";
    if (latestCall?.qualification && latestCall.qualification !== "unqualified") {
      tier = latestCall.qualification as LeadTier;
    } else if (latestCall?.qualification === "unqualified") {
      tier = "cold";
    } else {
      tier = tierFromScore(leadScore, leadStatus);
    }

    return {
      customer,
      latestCall,
      callCount: calls.length,
      leadScore,
      leadStatus,
      tier,
      lastContacted: latestCall?.created_at || null,
    };
  });
}

export const tierLabel: Record<LeadTier, string> = {
  hot: "Hot Lead",
  warm: "Warm Lead",
  cold: "Cold Lead",
  unscored: "Not Yet Scored",
};

export const tierTone: Record<LeadTier, "green" | "amber" | "red" | "gray"> = {
  hot: "green",
  warm: "amber",
  cold: "red",
  unscored: "gray",
};
