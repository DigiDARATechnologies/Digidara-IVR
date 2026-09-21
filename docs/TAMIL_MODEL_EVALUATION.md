# Tamil Realtime Model Evaluation

## Purpose

Decide whether `gpt-realtime-2.1-mini` can replace `gpt-realtime-2.1` for Tamil calls without an unacceptable loss in comprehension, factual accuracy, Tamil naturalness, turn handling, or call completion.

This is a controlled live-call test, not a comparison of unrelated historical calls. Only the Realtime conversation model changes. The Tamil transcription model, voice, prompt, campaign, caller, question order, approximate pacing, and environment must remain identical.

## Fixed test configuration

- Campaign: `AI System Engineer - Tamil`
- Language selection: press 2 for Tamil
- Tamil transcription: `gpt-4o-transcribe` for both calls
- Voice and conversation policy: unchanged for both calls
- Caller and receiving phone: the same person and number for both calls
- Target duration: approximately 4–5 minutes each
- Calls: one full-model call and one mini-model call, placed back-to-back
- Blinding: do not tell the caller which model is serving each call
- Production default: do not change it until the result passes the acceptance gate

## Caller script

Ask the following in order, using the same wording and similar pauses in both calls:

1. `AI System Engineer course syllabus எப்படி இருக்கும்?`
2. `Next batch எப்போது start ஆகும்?`
3. `இந்த course-ஐ hybrid mode-ல் படிக்க முடியுமா?`
4. `Fee structure மற்றும் payment options என்ன?`
5. `Free demo class கிடைக்குமா? எப்படி book பண்ணுவது?`
6. `Career counselling-க்கு appointment schedule பண்ண முடியுமா?`
7. While one normal answer is playing, interrupt once with: `ஒரு நிமிஷம், இதை short-ஆ சொல்லுங்க.`
8. End clearly with: `சரி, நன்றி. இப்போது call முடிக்கலாம். Goodbye.`

Do not add follow-up questions to only one call. If clarification is necessary, use the same clarification in the other call.

## Manual scorecard

Score each model independently immediately after its call.

| Dimension | Scoring |
|---|---|
| Question comprehension | 0 = missed/wrong, 1 = partly understood, 2 = correctly understood; score questions 1–6 |
| Factual accuracy | 0 = wrong/invented, 1 = incomplete/uncertain, 2 = correct and grounded; score questions 1–6 |
| Tamil naturalness | 1–5 overall |
| Clarity and pronunciation | 1–5 overall |
| Brevity | 1–5 overall; 5 means concise without losing the answer |
| Interruption handling | Pass if it stops cleanly and answers the interruption |
| Call termination | Pass if it gives one brief farewell and disconnects |

The application will provide model name, duration, total turns, interruptions, rejected false turns, average/first/maximum response latency, token counts, estimated OpenAI cost, and recorded Plivo cost from `call_logs` and `realtime_usage`.

## Acceptance gate for switching Tamil to mini

Mini may become the Tamil default only if all conditions pass:

- At least 10/12 total comprehension points.
- No critical factual error or fabricated course promise.
- At least 10/12 total factual-accuracy points.
- Tamil naturalness and clarity are each at least 4/5 and no more than 0.5 below the full model.
- Interruption handling and call termination both pass.
- No material turn-taking regression: false turns do not increase by more than one and average latency is not more than 20% worse.
- Cache-aware OpenAI estimated cost is at least 50% lower than the full-model call.

If the result is mixed, keep the full model as the default and repeat the pair with another Tamil speaker before deciding. Do not tune the production prompt between the two calls.

## Results

| Metric | Full model | Mini model |
|---|---:|---:|
| Call-log ID | Pending | Pending |
| Duration | Pending | Pending |
| Comprehension (/12) | Pending | Pending |
| Factual accuracy (/12) | Pending | Pending |
| Tamil naturalness (/5) | Pending | Pending |
| Clarity/pronunciation (/5) | Pending | Pending |
| Brevity (/5) | Pending | Pending |
| Interruption handling | Pending | Pending |
| Call termination | Pending | Pending |
| Average latency | Pending | Pending |
| First/maximum latency | Pending | Pending |
| False turns / interruptions | Pending | Pending |
| Estimated OpenAI cost | Pending | Pending |
| Recorded Plivo cost | Pending | Pending |
| Estimated OpenAI saving with mini | Pending | Pending |

## Operational decision — 2026-08-07

The product owner explicitly chose `gpt-realtime-2.1-mini` as the Tamil operational default before API credits were restored. This is a cost-led configuration decision, not a claim that the acceptance gate above has passed. The Tamil transcription model (`gpt-4o-transcribe`), built-in voice, prompt, knowledge behavior, and manual validated-turn policy remain unchanged.

When credits are available, run the same live-call scorecard against the new default and treat any material Tamil comprehension, naturalness, interruption, or termination regression as a rollback signal to `gpt-realtime-2.1`.

## Rollback decision — 2026-08-07

Two post-switch Tamil mini calls failed the operational quality gate. One lost the supplied campaign purpose and invented a test-call explanation; the next incorrectly treated the customer's `வணக்கம்` greeting as goodbye and invoked `end_call`. Tamil was therefore rolled back to `gpt-realtime-2.1`. English remains on mini.

Final decision: **Tamil uses `gpt-realtime-2.1`; mini may be reconsidered only after prompt/model improvements and controlled live validation.**
