export interface Customer {
  id: number;
  name: string;
  email: string;
  phone?: string | null;
  language?: string | null;
  investigated_course?: string | null;
  internship_or_course?: string | null;
  course_duration?: string | null;
  created_at: string;
}

export type CustomerPayload = Omit<Customer, "id" | "created_at">;

export interface Campaign {
  id: number;
  campaign_name: string;
  objective: string;
  ai_prompt: string;
}

export type CampaignPayload = Omit<Campaign, "id">;

export interface PhoneNumber {
  id: number;
  organization_id: number;
  campaign_id: number;
  plivo_number: string;
  label?: string | null;
  is_active: boolean;
  created_at: string;
}

export type PhoneNumberPayload = {
  plivo_number: string;
  campaign_id: number;
  label?: string | null;
  is_active?: boolean;
};

export type PhoneNumberUpdatePayload = Partial<
  Pick<PhoneNumberPayload, "campaign_id" | "label" | "is_active">
>;

export interface CallLog {
  id: number;
  customer_id?: number | null;
  campaign_id?: number | null;
  call_sid?: string | null;
  provider?: string | null;
  provider_request_id?: string | null;
  provider_call_id?: string | null;
  provider_stream_id?: string | null;
  provider_recording_id?: string | null;
  provider_status?: string | null;
  status?: string | null;
  call_status?: string | null;
  transcript?: string | null;
  summary?: string | null;
  quick_summary?: string | null;
  duration?: number | null;
  lead_score?: number | null;
  lead_status?: string | null;
  qualification?: "hot" | "warm" | "cold" | "unqualified" | string | null;
  language?: string | null;
  outcome?: string | null;
  failure_reason?: string | null;
  conversation_end_reason?: string | null;
  followup_required?: boolean;
  followup_date?: string | null;
  realtime_model?: string | null;
  realtime_voice?: string | null;
  voice_style_profile?: string | null;
  knowledge_profile?: string | null;
  conversation_profile?: string | null;
  turn_gate_profile?: string | null;
  avg_response_latency_ms?: number | null;
  first_response_latency_ms?: number | null;
  maximum_response_latency_ms?: number | null;
  estimated_openai_cost_usd?: number | null;
  estimated_twilio_cost_usd?: number | null;
  estimated_telephony_cost_usd?: number | null;
  input_audio_tokens?: number | null;
  output_audio_tokens?: number | null;
  input_text_tokens?: number | null;
  output_text_tokens?: number | null;
  interruption_count?: number | null;
  false_turn_count?: number | null;
  total_turns?: number | null;
  duration_minutes?: number | null;
  turns_per_minute?: number | null;
  interruptions_per_minute?: number | null;
  estimated_total_inr?: number | null;
  estimated_cost_per_minute_inr?: number | null;
  is_abnormal?: boolean;
  abnormal_reasons?: string[];
  call_duration_limit_seconds?: number | null;
  recording_sid?: string | null;
  recording_status?: string | null;
  recording_duration_seconds?: number | null;
  created_at?: string | null;
}

export interface Department {
  id: number;
  organization_id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
  member_count: number;
  created_at: string;
  updated_at: string;
}

export interface StaffDestination {
  id: number;
  organization_id: number;
  name: string;
  phone_e164: string;
  department?: string | null;
  priority: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CallTransfer {
  id: number;
  organization_id: number;
  call_log_id: number;
  destination_id: number;
  destination_name?: string | null;
  destination_phone?: string | null;
  department?: string | null;
  status: "requested" | "provider_accepted" | "ringing" | "answered" | "completed" | "failed" | "cancelled";
  provider_call_id: string;
  provider_bleg_id?: string | null;
  initiated_by_user_id: number;
  failure_reason?: string | null;
  requested_at: string;
  answered_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
}

export interface IvrOption {
  id?: number;
  digit: string;
  label: string;
  campaign_id?: number | null;
  destination_id?: number | null;
  destination_name?: string | null;
  destination_phone?: string | null;
  is_active: boolean;
  sort_order: number;
}

export interface IvrSettings {
  is_active: boolean;
  timeout_seconds: number;
  prompt_english: string;
  prompt_tamil: string;
  options: IvrOption[];
}

export type CallbackStatus = "pending" | "assigned" | "completed" | "cancelled";

export interface CallbackTask {
  id: number;
  organization_id: number;
  customer_id: number;
  campaign_id?: number | null;
  source_call_log_id?: number | null;
  reminder_type: string;
  source: string;
  requested_date?: string | null;
  scheduled_at?: string | null;
  timezone: string;
  status: CallbackStatus;
  assigned_user_id?: number | null;
  assigned_user_name?: string | null;
  notes?: string | null;
  completed_at?: string | null;
  completed_by_user_id?: number | null;
  customer_name: string;
  customer_phone?: string | null;
  call_summary?: string | null;
  lead_score?: number | null;
  qualification?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CallbackSummary {
  pending: number;
  assigned: number;
  overdue: number;
  due_today: number;
  completed: number;
}

export interface CallbackUpdate {
  status?: CallbackStatus;
  assigned_user_id?: number;
  clear_assignee?: boolean;
  requested_date?: string;
  scheduled_at?: string;
  clear_schedule?: boolean;
  notes?: string;
}

export interface LeadQualification {
  id: number;
  call_log_id: number;
  customer_id: number;
  customer_name?: string | null;
  customer_email?: string | null;
  extracted_name?: string | null;
  extracted_phone?: string | null;
  company?: string | null;
  requirement?: string | null;
  budget?: string | null;
  timeline?: string | null;
  lead_score?: number | null;
  qualification?: "hot" | "warm" | "cold" | "unqualified" | null;
  created_at?: string | null;
}

export interface CustomerMemory {
  id?: number;
  customer_id: number;
  name?: string | null;
  intent?: string | null;
  previous_questions?: string[];
  lead_status?: string | null;
  summary?: string | null;
  updated_at?: string | null;
}

export interface KBDocument {
  id: string;
  preview: string;
  metadata?: Record<string, string>;
}

export interface KBStatus {
  available: boolean;
  error?: string | null;
  collections: string[];
}

export interface StartCallResponse {
  message: string;
  call_sid: string | null;
  status: "initiated" | "simulated" | "failed" | string;
  provider?: string;
  provider_call_id?: string | null;
  request_id?: string | null;
}

export interface RunSheetRequest {
  sheet_url: string;
  campaign_id: number;
}

export interface RunSheetResult {
  message: string;
  calls_triggered?: Array<Record<string, string | number | null>>;
  sheet_url?: string;
}

export interface SheetStatusRow {
  row_number: number;
  name: string;
  phone: string;
  language: string;
  status: string;
}

export interface SheetStatusResult {
  rows: SheetStatusRow[];
}

export interface ChatResponse {
  reply?: string;
  error?: string;
}

export interface LeadScoreRequest {
  interested: boolean;
  budget: boolean;
  decision_maker: boolean;
  callback_requested: boolean;
}

export interface LeadScoreResponse {
  lead_score: number;
  status: string;
  source: "manual_preview";
  persisted: false;
}

export interface ApiErrorBody {
  detail?: string;
  error?: string;
  message?: string;
}
