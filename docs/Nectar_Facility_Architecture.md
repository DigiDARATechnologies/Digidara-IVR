# Nectar Facility Operations Architecture

The Nectar product is a separate Facility Operations bounded context inside the
existing voice platform. It does not alter the active DigiDARA sales-call
pipeline (`app/api/plivo.py` and `app/api/openai_realtime.py`).

## Implemented module structure

```text
app/
  api/
    facility.py                 # HTTP adapter only: auth, dependencies, response shape
  facility/
    domain/
      contracts.py              # shared typed vocabulary and API/MCP contracts
    application/
      facility_queries.py       # read use cases
      demo_scenario.py          # explicit Building A challenge fixture use case
      facility_tools.py         # evidence-only MCP tool use cases
      service_request_actions.py # single-use confirmation-gated write use case
    infrastructure/
      repository.py             # parameterized MySQL access and tenant joins
    mcp/
      server.py                 # authenticated MCP server factory
    rag/
      service.py                # isolated Chroma collection, citations, no-answer guardrail
      seed_documents.py         # reviewed HVAC and safety documents for the demo
    orchestration/
      routing.py                # structured LLM routing with a safe fallback
      hvac_investigation.py     # evidence-only multi-step HVAC workflow
  schemas/
    facility.py                 # temporary compatibility exports
  services/
    facility_service.py         # temporary compatibility facade
  database/
    db.py                       # development-safe schema bootstrap
migrations/
  20260819_nectar_facility_foundation_*.sql
tests/
  test_facility_foundation.py
```

The compatibility modules allow current imports to continue working. New
Facility code must import from `app.facility`, not add functions to the facade.
They can be removed only after all consumers are migrated.

## Planned structure as modules are implemented

```text
app/facility/
  domain/                       # types, policy invariants, immutable contracts
  application/                  # use cases: query, diagnose, confirm, create request
  infrastructure/               # MySQL repository and real BMS/CMMS adapters
  mcp/                          # MCP tool definitions and transport adapter
  rag/                          # document ingestion, retrieval, citations, grounding policy
  orchestration/                # route decision, agent state machine, tool execution policy
  evaluation/                   # repeatable route/RAG/tool safety evaluations
src/features/facility/          # React feature: API client, hooks, console components
```

Folders are added with their concrete implementation rather than pre-created
empty, so the architecture stays intentional and discoverable.

## Dependency rules

```text
FastAPI / React adapters -> application use cases -> domain + infrastructure
MCP tools               -> application use cases -> domain + infrastructure
orchestration           -> MCP + RAG + application
```

- Only `infrastructure/repository.py` may issue Facility SQL.
- Every repository query scopes through `facility_sites.organization_id`.
- Router handlers remain thin and never choose tools or build agent prompts.
- MCP write tools will be confirmation-gated in the application layer; a model
  cannot create a maintenance request directly.
- The current MCP server exposes evidence-only read tools. It is built for an
  authenticated organization context rather than accepting a tenant identifier
  from the MCP client; transport mounting follows the confirmation workflow.
- The facility RAG corpus will be separate from the sales knowledge bases.
- Routing is LLM-first through a strict JSON-schema response. If the provider
  is unavailable or returns low-confidence output, a deterministic fallback
  selects a safe information route and always marks possible write actions for
  confirmation.

## Production delivery boundaries

The current Building A records are demo data created only by an authenticated
endpoint. Production BMS/CMMS integration will use environment-backed
credentials and audited adapter calls; raw credentials and operational actions
will never be exposed to the voice model or browser.

## Current operator surface

`POST /facility/agent/query` is the backend facade for the Facility Voice
Console. It returns the route chosen, concise grounded response, citations, and
whether an explicit maintenance confirmation is required. The React console is
available at `/facility-console`; browser speech recognition is a convenience
input option, while the established Plivo/OpenAI Realtime path remains the
production telephone transport until the Facility session adapter is added.
