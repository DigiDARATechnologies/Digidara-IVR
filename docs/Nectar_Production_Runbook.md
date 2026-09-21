# Nectar Facility Operations Production Runbook

## Required configuration

Use a secret manager or deployment environment variables for `OPENAI_API_KEY`,
`DB_PASSWORD`, `MYSQL_ROOT_PASSWORD`, Plivo credentials, and the stable public
webhook/stream URLs. Never add them to this repository or the Docker image.

The Facility Agent additionally accepts `FACILITY_ROUTER_MODEL`; if it is not
set, it uses `OPENAI_CHAT_MODEL`. Use a pinned, approved model identifier for a
production release and run the evaluation suite before changing it.

## Local validation

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_facility*.py" -q
npm ci
npm run build
```

## Container validation

Start Docker Desktop, create a local `.env` with non-production database
passwords, then run:

```powershell
docker compose build
docker compose up -d
```

Validate `GET /docs`, authenticate, then call `POST /facility/demo/seed` and
`POST /facility/agent/query`. A production deployment must use a stable HTTPS
domain; never use a development tunnel as Plivo callback infrastructure.

## Release gates

1. All Facility tests and frontend build pass.
2. The route evaluation set passes for the configured router model and safe
   fallback.
3. A manually approved service request is created once, audited once, and
   cannot be recreated with the same confirmation ID.
4. Facility RAG returns citations for a supported procedure and declines an
   unsupported question.
5. A real authenticated MCP host integration and a controlled phone-call test
   are run in staging before any production facility action is enabled.

## Known verification boundary

This repository validates the Facility domain, MCP tool registration, RAG,
routing, orchestration, API contracts, and browser console offline. It does not
validate a real BMS/CMMS, OpenAI request, Plivo call, or deployed Docker image
until the environment credentials, stable ingress, and approved test account
are provided.

For the local acceptance workflow, copy `.env.example` to `.env` and set the
working local MySQL credentials before starting Uvicorn. `.env` is ignored by
Git and must not be shared in chat or committed.
