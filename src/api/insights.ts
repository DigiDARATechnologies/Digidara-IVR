import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export interface DashboardSummary {
  customers:number; campaigns:number; total_calls:number; answered_calls:number;
  qualified_leads:number; answer_rate:number; conversion_rate:number;
  avg_response_latency_ms:number; avg_duration_seconds:number; english_calls:number;
  tamil_calls:number; live_calls:number; estimated_openai_cost_usd:number;
  estimated_telephony_cost_usd:number;
  openai_estimated_usd:number; openai_estimated_inr:number;
  plivo_recorded_usd:number; plivo_recorded_inr:number;
  total_estimated_inr:number; openai_usd_to_inr:number; plivo_usd_to_inr:number;
  campaign_performance:Array<{id:number;campaign_name:string;calls:number;qualified:number}>;
}
export const useDashboardSummary=()=>useQuery({queryKey:["dashboard-summary"],queryFn:async()=> (await api.get<DashboardSummary>("/dashboard/summary")).data,refetchInterval:15000});
export const useSystemData=(type:string)=>useQuery({queryKey:["system",type],queryFn:async()=> (await api.get<any[]>(`/system/${type}`)).data});
export interface ProviderCostPresentation {openai_estimated_usd:number;openai_estimated_inr:number;plivo_recorded_usd:number;plivo_recorded_inr:number;total_estimated_inr:number;openai_usd_to_inr:number;plivo_usd_to_inr:number}
export interface UsageCustomer extends ProviderCostPresentation {id:number;name:string;calls:number;seconds:number;tokens:number;openai_usd:number;telephony_usd:number;total_usd:number;total_inr:number}
export interface UsageSummary extends ProviderCostPresentation {calls:number;seconds:number;tokens:number;openai_usd:number;telephony_usd:number;total_usd:number;total_inr:number;usd_to_inr:number;customers:UsageCustomer[]}
export interface AnalyticsReport {campaigns:Array<ProviderCostPresentation&{id:number;campaign_name:string;calls:number;completed:number;qualified:number;seconds:number;openai_usd:number;telephony_usd:number;cost_usd:number;conversion_rate:number;cost_per_qualified_usd:number;cost_per_qualified_inr:number}>;customers:Array<ProviderCostPresentation&{id:number;name:string;language:string;calls:number;latest_qualification:string;seconds:number;openai_usd:number;telephony_usd:number;cost_usd:number}>}
export const useUsageSummary=()=>useQuery({queryKey:["usage-summary"],queryFn:async()=> (await api.get<UsageSummary>("/usage/summary")).data,refetchInterval:15000});
export const useAnalyticsReport=()=>useQuery({queryKey:["analytics-report"],queryFn:async()=> (await api.get<AnalyticsReport>("/analytics/report")).data,refetchInterval:15000});
