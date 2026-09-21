from pydantic import BaseModel, Field
from typing import Optional

class CallLogBase(BaseModel):
    customer_id: Optional[int] = Field(None, description="The ID of the customer associated with the call")
    campaign_id: Optional[int] = Field(None, description="The ID of the campaign associated with the call")
    call_sid: Optional[str] = Field(None, description="Historical provider ID compatibility alias")
    provider: Optional[str] = None
    provider_request_id: Optional[str] = None
    provider_call_id: Optional[str] = None
    provider_stream_id: Optional[str] = None
    provider_recording_id: Optional[str] = None
    provider_status: Optional[str] = None
    stream_status: Optional[str] = None
    correlation_id: Optional[str] = None
    status: Optional[str] = Field(None, description="The status of the call (from SQLite schema)")
    call_status: Optional[str] = Field(None, description="The status of the call (from MySQL schema)")
    lead_score: Optional[int] = Field(None, description="AI-derived lead score 0-100, generated after call analysis")
    lead_status: Optional[str] = Field(None, description="AI-derived lead status: interested, not_interested, callback_requested, no_answer, completed")
    transcript: Optional[str] = Field(None, description="The call audio transcription")
    summary: Optional[str] = Field(None, description="Summary of the call conversation")
    duration: Optional[int] = Field(None, description="Duration of the call in seconds")
    call_path: Optional[str] = Field(None, description="Call engine path: relay, media_stream, media_stream_ta, or gather")
    stt_confidence_avg: Optional[float] = Field(None, description="Average STT confidence for media-stream calls")
    tts_provider: Optional[str] = Field(None, description="Tamil STT/TTS provider used for the call")
    stt_provider: Optional[str] = None
    llm_provider: Optional[str] = None
    voice_provider: Optional[str] = None
    realtime_model: Optional[str] = None
    transcription_model: Optional[str] = None
    realtime_voice: Optional[str] = None
    voice_style_profile: Optional[str] = None
    knowledge_profile: Optional[str] = None
    conversation_profile: Optional[str] = None
    turn_gate_profile: Optional[str] = None
    language: Optional[str] = None
    qualification: Optional[str] = None
    quick_summary: Optional[str] = None
    outcome: Optional[str] = None
    failure_reason: Optional[str] = None
    conversation_end_reason: Optional[str] = None
    followup_required: bool = False
    followup_date: Optional[str] = None
    joining_date: Optional[str] = None
    reminder_consent: Optional[str] = None
    reminder_call_date: Optional[str] = None
    first_response_latency_ms: Optional[int] = None
    avg_response_latency_ms: Optional[int] = None
    maximum_response_latency_ms: Optional[int] = None
    estimated_openai_cost_usd: Optional[float] = None
    estimated_twilio_cost_usd: Optional[float] = None
    estimated_telephony_cost_usd: Optional[float] = None
    provider_bill_duration_seconds: Optional[int] = None
    input_audio_tokens: Optional[int] = None
    output_audio_tokens: Optional[int] = None
    input_text_tokens: Optional[int] = None
    output_text_tokens: Optional[int] = None
    recording_sid: Optional[str] = None
    recording_status: Optional[str] = None
    recording_duration_seconds: Optional[int] = None
    recording_channels: Optional[int] = None
    total_turns: Optional[int] = None
    interruption_count: Optional[int] = None
    false_turn_count: Optional[int] = None
    duration_minutes: Optional[float] = None
    turns_per_minute: Optional[float] = None
    interruptions_per_minute: Optional[float] = None
    estimated_total_inr: Optional[float] = None
    estimated_cost_per_minute_inr: Optional[float] = None
    is_abnormal: bool = False
    abnormal_reasons: list[str] = Field(default_factory=list)
    call_duration_limit_seconds: Optional[int] = None
    started_at: Optional[str] = None
    answered_at: Optional[str] = None
    completed_at: Optional[str] = None

class CallLogCreate(CallLogBase):
    pass

class CallLogResponse(CallLogBase):
    id: int
    created_at: Optional[str] = Field(None, description="Timestamp when the call log was created")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "customer_id": 5,
                "campaign_id": 2,
                "call_sid": "mock_call_1780452702_d3e530f7",
                "status": "initiated",
                "call_status": "in-progress",
                "transcript": "Hello, are you interested in our software?",
                "summary": "Customer answered and was interested.",
                "duration": 45,
                "call_path": "media_stream_ta",
                "stt_confidence_avg": 0.82,
                "tts_provider": "gemini",
                "created_at": "2026-06-03 07:41:42"
            }
        }
