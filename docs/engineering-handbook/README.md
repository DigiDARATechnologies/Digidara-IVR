# DigiDARA — AI Voice Sales Agent

Bilingual (English/Tamil) AI voice calling platform for outbound lead qualification. DigiDARA places real phone calls, holds a natural speech-to-speech conversation grounded in an approved knowledge base, and hands qualified leads back to a human counselling team.

## What it does

- Places outbound calls via Plivo and carries on a live, low-latency conversation via OpenAI's Realtime API — speech-to-speech, not a record-transcribe-synthesize pipeline.
- Lets the customer choose their spoken language at the start of the call with a DTMF menu ("Press 1 for English, Press 2 for Tamil").
- Answers course/fee/batch questions from an approved, per-language knowledge base — it does not invent facts.
- Judges for itself, from conversational context, when the customer wants to end the call, and closes gracefully with a short goodbye in the right language.
- Works through a Google Sheet of leads automatically: creates/updates CRM records, skips numbers on the do-not-call list, dials the next lead, and writes call status back to the sheet.
- Tracks true per-call cost (telephony minutes plus Realtime and transcription token usage) so unit economics are visible per call, campaign, and organization.

## Status

This is a working prototype with a real, exercised production call path — not a concept demo — and a set of known, tracked gaps (multi-tenant enforcement, CI, pinned dependencies) documented honestly in [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md) rather than hidden. See [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) for the full picture and [`FUTURE_VISION.md`](FUTURE_VISION.md) for where it's headed.

## Tech Stack

**Backend:** Python, FastAPI, MySQL 8 (raw parameterized SQL via PyMySQL, no ORM), PyJWT + bcrypt, `websockets`, Plivo SDK, `gspread`/`google-auth`.
**Frontend:** React 18, TypeScript, Vite, Tailwind CSS, `@tanstack/react-query`, `recharts`.
**Voice/AI:** Plivo (telephony, Audio Streaming, signed webhooks), OpenAI Realtime API (conversation engine, both languages).

## Getting Started

### Prerequisites

- Python 3.11+ and a virtual environment
- Node.js 18+ and npm
- MySQL 8, reachable locally or remotely
- A Plivo account (Auth ID/Token, a Plivo number)
- An OpenAI API key with Realtime API access
- (Optional, for bulk-calling write-back) A Google Cloud service account with Sheets/Drive API access

### Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd DigiDARA-AI-VOICE-AGENT

# 2. Backend environment
python -m venv venv
./venv/Scripts/activate        # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r app/requirements.txt

# 3. Frontend dependencies
npm ci

# 4. Environment configuration
cp .env.example .env
# Fill in: DB_*, OPENAI_API_KEY, PLIVO_*, and generate secrets:
python -c "import secrets; print(secrets.token_urlsafe(48))"   # for JWT_SECRET and DATA_ENCRYPTION_KEY

# 5. Database
mysql -u root -p < schema.sql
# apply anything under migrations/ as well

# 6. Seed an admin account
python seed.py
```

### Running locally

```bash
# Backend
uvicorn app.main:app --reload

# Frontend (separate terminal)
npm run dev

# Public webhook tunnel for Plivo (separate terminal, development only)
cloudflared tunnel --url http://localhost:8000
# Copy the printed https://<random>.trycloudflare.com hostname into .env's
# WEBHOOK_BASE_URL and PLIVO_STREAM_BASE_URL — this changes every time the
# tunnel restarts, so re-check it if a call fails with a "ValidationError".
```

### Running tests

```bash
python -m unittest discover -s tests -q
```

Uses Python's built-in `unittest`, not `pytest` (not installed). As of 2026-08-05, 102 tests pass.

## Bulk Calling (Google Sheets)

To run an automated campaign against a lead list:

1. Prepare a sheet with recognizable columns — Name, Phone (accepts several header variants — see `normalize_headers()` in `app/services/google_sheets_service.py`), and optionally Language and Status.
2. For status write-back (marking rows as called/skipped as the campaign progresses), place a Google service-account `credentials.json` in the repo root and share the sheet with that account's email as an Editor. Without it, the sheet can still be **read** via a public CSV-export fallback, but status **write-back will fail**.
3. Trigger the campaign from the Bulk Calling page in the UI, or via `POST /calls/run-sheet`.

Do-not-call and suppression checks run automatically before every dial — a suppressed lead is skipped and marked, never called.

## Documentation

This repository is accompanied by a full engineering documentation set:

| Document | Purpose |
|---|---|
| [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) | Vision, status, roadmap, stack, principles |
| [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) | Full architecture, module boundaries, sequence diagrams |
| [`ARCHITECTURE_DECISION_RECORD.md`](ARCHITECTURE_DECISION_RECORD.md) | Every major architectural decision, with reasoning and tradeoffs |
| [`ENGINEERING_GUIDELINES.md`](ENGINEERING_GUIDELINES.md) | Coding, security, testing, and review standards |
| [`ENGINEERING_ROADMAP.md`](ENGINEERING_ROADMAP.md) | Epics, priorities, sequencing |
| [`SECURITY_GUIDE.md`](SECURITY_GUIDE.md) | Auth, tenancy, secrets, OWASP posture |
| [`DATABASE_ARCHITECTURE.md`](DATABASE_ARCHITECTURE.md) | Full schema reference |
| [`VOICE_PLATFORM.md`](VOICE_PLATFORM.md) | Telephony and call-lifecycle detail |
| [`AI_PLATFORM.md`](AI_PLATFORM.md) | Conversation engine, prompts, tools |
| [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) | Environments, config, target deployment |
| [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md) | Test framework and coverage approach |
| [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) | Folder-by-folder map |
| [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md) | Known gaps, ranked by risk |
| [`IMPLEMENTATION_CHECKLIST.md`](IMPLEMENTATION_CHECKLIST.md) | Actionable stories/tasks per roadmap epic |
| [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md) | Monitoring, incidents, recovery |
| [`FUTURE_VISION.md`](FUTURE_VISION.md) | Prototype → Global AI Platform |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to contribute |
| [`CHANGELOG.md`](CHANGELOG.md) | Milestones |
| [`AI_ENGINEERING_CONTEXT.md`](AI_ENGINEERING_CONTEXT.md) | Context for AI coding assistants working in this repo |
| [`MASTER_INDEX.md`](MASTER_INDEX.md) | Full index of the documentation set |

## License

Proprietary — DigiDara Technologies. All rights reserved.
