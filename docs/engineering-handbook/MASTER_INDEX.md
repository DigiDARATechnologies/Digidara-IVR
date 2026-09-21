# DigiDARA — Master Documentation Index

This is the entry point to DigiDARA's engineering documentation package: 21 documents covering vision, architecture, security, database, voice/AI platforms, deployment, testing, roadmap, and AI-assistant context. Read [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) first if you are new to the project; use the table below to find everything else by purpose.

| # | Document | Purpose | Audience | Depends On | Read When |
|---|---|---|---|---|---|
| 1 | [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | Business/product vision, current status, roadmap summary, stack, principles | Everyone — engineers, new hires, stakeholders | None | First — always start here |
| 2 | [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | Full architecture: modules, layers, sequence diagrams | Engineers, architects | PROJECT_OVERVIEW | Before working in any part of the codebase for the first time |
| 3 | [ARCHITECTURE_DECISION_RECORD.md](ARCHITECTURE_DECISION_RECORD.md) | Why the architecture is the way it is — decisions, tradeoffs, alternatives | Engineers, architects, reviewers | SYSTEM_ARCHITECTURE | Before changing or questioning an existing architectural pattern |
| 4 | [ENGINEERING_GUIDELINES.md](ENGINEERING_GUIDELINES.md) | Coding, security, testing, review, naming, folder standards | All engineers | PROJECT_OVERVIEW | Before writing any code in this repository |
| 5 | [ENGINEERING_ROADMAP.md](ENGINEERING_ROADMAP.md) | Epics, stories, priority, risk, sequencing | Engineering leads, planners | ARCHITECTURE_DECISION_RECORD, TECHNICAL_DEBT | When planning what to work on next |
| 6 | [SECURITY_GUIDE.md](SECURITY_GUIDE.md) | Auth, tenancy, secrets, OWASP posture, incident response | Engineers, security reviewers | SYSTEM_ARCHITECTURE, DATABASE_ARCHITECTURE | Before touching auth, credentials, or tenant-scoped data |
| 7 | [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md) | Full schema reference, tenancy scoping, indexes, retention | Engineers, DBAs | SYSTEM_ARCHITECTURE | Before writing any query or migration |
| 8 | [VOICE_PLATFORM.md](VOICE_PLATFORM.md) | Telephony/Plivo integration, call lifecycle, language selection | Voice/telephony engineers | SYSTEM_ARCHITECTURE | Before touching `app/api/plivo.py` or `plivo_stream.py` |
| 9 | [AI_PLATFORM.md](AI_PLATFORM.md) | OpenAI Realtime integration, prompts, memory, tools | AI/conversation engineers | SYSTEM_ARCHITECTURE, VOICE_PLATFORM | Before touching `openai_realtime.py` or `conversation_policy_service.py` |
| 10 | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Dev setup, environments, config, target production shape | Engineers, DevOps | PROJECT_OVERVIEW | When setting up a new environment or planning deployment |
| 11 | [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Test framework, coverage approach, near-term gaps | All engineers | ENGINEERING_GUIDELINES | Before writing or reviewing any test |
| 12 | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Folder-by-folder map, module ownership | New engineers | SYSTEM_ARCHITECTURE | When deciding where new code belongs |
| 13 | [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md) | Known gaps ranked by risk | Engineers, planners | ARCHITECTURE_DECISION_RECORD | Before assuming something is a bug versus a tracked gap |
| 14 | [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) | Every roadmap epic as concrete stories/tasks/acceptance criteria | Engineers executing roadmap work | ENGINEERING_ROADMAP | When starting work on a specific roadmap item |
| 15 | [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) | Monitoring, incidents, backup/recovery, provider outages | On-call engineers, ops | VOICE_PLATFORM, SECURITY_GUIDE | During an incident, or when setting up monitoring |
| 16 | [FUTURE_VISION.md](FUTURE_VISION.md) | Prototype → Production MVP → Commercial → Enterprise → Global Platform | Leadership, engineers, planners | ENGINEERING_ROADMAP, TECHNICAL_DEBT | When making a build-vs-defer call against the long-term direction |
| 17 | [README.md](README.md) | Project introduction, quickstart, bulk-calling guide | New engineers, external readers | None | First contact with the repository |
| 18 | [CONTRIBUTING.md](CONTRIBUTING.md) | Branching, review, testing, documentation expectations | Contributors | ENGINEERING_GUIDELINES | Before opening a pull request |
| 19 | [CHANGELOG.md](CHANGELOG.md) | Architecturally significant milestones, fixed/added/investigated | Everyone | None | To understand recent history without reading git log |
| 20 | [AI_ENGINEERING_CONTEXT.md](AI_ENGINEERING_CONTEXT.md) | Rules and context for AI coding assistants working in this repo | Claude Code, Codex, Copilot, Cursor, Windsurf, Gemini CLI, and any AI assistant | All of the above | Before an AI assistant makes any change to this repository |
| 21 | [AI_WORK_SESSION_LOG.md](../AI_WORK_SESSION_LOG.md) | Chronological implementation, verification, publication, and handoff record for AI-assisted work | AI assistants and contributors resuming prior work | AI_ENGINEERING_CONTEXT | Before resuming work from a previous AI session and after every meaningful change |

## Suggested Reading Paths

**New human engineer, first week:** PROJECT_OVERVIEW → SYSTEM_ARCHITECTURE → PROJECT_STRUCTURE → ENGINEERING_GUIDELINES → DEPLOYMENT_GUIDE (to get running locally) → whichever platform doc matches your first task.

**Engineer picking up a roadmap item:** ENGINEERING_ROADMAP → IMPLEMENTATION_CHECKLIST (find your story) → the relevant platform doc → ARCHITECTURE_DECISION_RECORD (check if your area has a documented decision already) → TESTING_STRATEGY.

**Security/compliance reviewer:** SECURITY_GUIDE → DATABASE_ARCHITECTURE (tenancy scoping) → ARCHITECTURE_DECISION_RECORD (ADR-008 specifically) → TECHNICAL_DEBT → OPERATIONS_RUNBOOK (incident response).

**AI coding assistant, any task:** AI_ENGINEERING_CONTEXT first, always — then read AI_WORK_SESSION_LOG for the latest handoff context before using the other documents relevant to the area being touched.

**On-call / incident response:** OPERATIONS_RUNBOOK → VOICE_PLATFORM or DATABASE_ARCHITECTURE (depending on the incident) → SECURITY_GUIDE (if the incident has a security dimension).

## A Note on How This Package Was Built

This documentation is grounded in the actual, verified state of the DigiDARA codebase — its real schema (inspected directly), its real endpoints and services (read directly), its real test suite (run directly, 86 passing tests), and the concrete, fully-detailed engineering work completed during the pass that produced this package (bilingual conversation architecture, AI-judged call termination, DNC/suppression enforcement, cost tracking, DTMF language selection, campaign-automation fixes). Forward-looking sections (roadmap sequencing, future-vision stages) are clearly presented as recommendations grounded in this real system, not as a record of decisions that cannot be independently verified. Keep this document current as new documentation is added or existing documents are substantially revised — a stale index is worse than no index.
