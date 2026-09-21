# DigiDARA — Deployment Guide

## Current State (Honest Baseline)

DigiDARA supports both a developer-operated local environment and a containerized runtime. Local development commonly uses MySQL 8, FastAPI through `uvicorn`, the Vite dev server, and a Cloudflare Quick Tunnel for Plivo callbacks. The repository also includes a non-root backend Docker image, Compose services for the API, CRM delivery worker, and MySQL, public liveness/readiness probes, and GitHub Actions for backend tests and the frontend build. A stable production ingress, managed database/backup policy, secret-store integration, and automated deployment pipeline remain deployment responsibilities rather than repository-provided infrastructure.

## Development

1. Clone the repository; copy `.env.example` to `.env` and fill in real values (DB credentials, `OPENAI_API_KEY`, Plivo credentials, a generated `JWT_SECRET`/`DATA_ENCRYPTION_KEY` — generate these with `python -c "import secrets; print(secrets.token_urlsafe(48))"`, never reuse the placeholder text from `.env.example`).
2. Create and activate a Python virtual environment; install the pinned backend dependencies from `app/requirements.txt`.
3. `npm install` for the frontend.
4. Ensure a MySQL 8 instance is reachable with the credentials in `.env`; apply `schema.sql` and anything under `migrations/`.
5. Run `python seed.py` to create the initial admin account (uses `ADMIN_BOOTSTRAP_KEY`-independent direct seeding, distinct from the `/auth/bootstrap-admin` API path — verify which one your environment actually uses and rotate the resulting credentials before anything but local use).
6. Start the backend: `uvicorn app.main:app --reload` (or the project's documented equivalent).
7. Start the frontend: `npm run dev`.
8. Start a public tunnel for Plivo webhooks: `cloudflared tunnel --url http://localhost:8000`, then copy the generated `https://<random>.trycloudflare.com` hostname into `.env`'s `WEBHOOK_BASE_URL` and `PLIVO_STREAM_BASE_URL` (the latter with `wss://` implied — the codebase derives the WebSocket scheme from the HTTPS one). **This hostname changes every time the tunnel process restarts** — a stale hostname in `.env` after a tunnel restart is the single most common cause of a live call failing with a Plivo `ValidationError` during development; always confirm the tunnel is currently running and `.env` matches its current hostname before debugging a call-creation failure as anything more exotic.
9. If testing bulk-calling / Google Sheets write-back, place a Google service-account `credentials.json` in the repository root (never commit it — it is `.gitignore`d) and share the target sheet with that service account's email as an Editor.

## Testing

Run the backend test suite with `python -m unittest discover -s tests -q` (not `pytest` — it is not installed; see [TESTING_STRATEGY.md](#)). Run the frontend type-check/build with `tsc -b && vite build` to catch TypeScript errors before considering a frontend change complete; there is currently no separate frontend unit-test runner configured.

## Production Deployment Requirements

The application runtime is container-ready; the following external infrastructure is still required for a production deployment:

- **Containerization:** build the included backend image for the API and CRM worker, and serve the frontend production build behind a standard web server or CDN.
- **Stable ingress:** a real domain with a managed TLS certificate and a persistent reverse proxy or load balancer in front of the backend, replacing the Cloudflare Quick Tunnel entirely for any non-local environment. Quick Tunnels are explicitly designed to be ephemeral and are not a supported production ingress mechanism.
- **Managed MySQL:** a managed database instance with automated backups, rather than a local unmanaged instance, once any real customer data exists outside a developer's machine.
- **Secrets:** environment variables injected by the deployment platform's secret store, never a committed `.env` file, with `credentials.json`-equivalent provisioning handled per-environment (see [ENGINEERING_ROADMAP.md](#) Epic D).

## Docker

The repository includes a non-root backend Docker image and Compose services for API, CRM worker, and MySQL. The API exposes `GET /health/live` and database-aware `GET /health/ready`; Compose gates API health on readiness, and the CRM worker writes a database heartbeat. Production deployment should still:

- Install dependencies from the pinned manifest ([TECHNICAL_DEBT.md](#) closes the prerequisite gap for this).
- Run as a non-root user.
- Read all configuration from environment variables, with no local-path assumptions (`find_credentials_file()`'s local-directory search behavior should be reviewed for container-friendliness — an explicit `GOOGLE_APPLICATION_CREDENTIALS` env var pointing at a mounted secret is the container-appropriate path, and is already the first thing that function checks).

## Environment Variables

Every variable the backend reads should be documented in `.env.example`, including its purpose, units, and default if any — this is already the standard the codebase holds itself to (e.g., the transcription cost-rate variables added during this engineering pass are documented with an explicit note to "verify against OpenAI's current pricing and override here if they drift"). Key variables by concern:

- **Database:** `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`.
- **Auth:** `JWT_SECRET`, `DATA_ENCRYPTION_KEY`, `ADMIN_BOOTSTRAP_KEY`.
- **OpenAI:** `OPENAI_API_KEY`, model selection variables, `OPENAI_TRANSCRIBE_AUDIO_INPUT_USD_PER_M` / `OPENAI_TRANSCRIBE_TEXT_OUTPUT_USD_PER_M` (transcription billing rates), `OPENAI_SERVER_VAD_SILENCE_MS_ENGLISH`, and `OPENAI_VAD_EAGERNESS_TAMIL`.
- **Plivo:** `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_STREAM_TOKEN_SECRET` (falls back to `PLIVO_AUTH_TOKEN` then `JWT_SECRET` if unset — set it explicitly in any real environment rather than relying on the fallback chain), `PLIVO_VALIDATE_SIGNATURES` (default `true`; do not set `false` outside local development), `WEBHOOK_BASE_URL`, `PLIVO_STREAM_BASE_URL`.
- **Google Sheets:** `GOOGLE_APPLICATION_CREDENTIALS` (path override for `credentials.json`).
- **CRM delivery worker:** `CRM_WORKER_POLL_SECONDS`, `CRM_WORKER_BATCH_SIZE`, and the retry/lease variables documented in `env.example`.
- **Environment mode:** `ENVIRONMENT` (`development` relaxes signature-validation defaults; any other value should be treated as production-grade and does not allow that relaxation).

## Configuration

Configuration is entirely environment-variable-driven with in-code defaults for non-secret values (e.g., `TAMIL_TTS_SPEAKER` defaults to `"Kore"` if unset). There is no separate configuration-file layer (no `config.yaml`/`settings.toml`) — this is an appropriate level of complexity for the current single-environment deployment and should remain env-var-driven rather than introducing a config-file layer with no current second-environment need to justify it.

## Deployment Flow (Target)

1. Merge to the main branch triggers CI (test suite + frontend build) — see [TESTING_STRATEGY.md](#) and [ENGINEERING_ROADMAP.md](#) Epic B.
2. On green CI, build and tag a container image.
3. Apply any pending database migrations (additive-first, per [DATABASE_ARCHITECTURE.md](#)'s migration strategy) before rolling out the new application version.
4. Roll out the new image behind the stable ingress, with health checks gating traffic cutover.
5. Verify: run a synthetic test call (or, at minimum, confirm webhook signature validation succeeds against the new deployment) before considering the deploy complete — a silent webhook-validation misconfiguration would otherwise only surface when a real customer call fails.

## Rollback Strategy (Target)

No automated rollback tooling exists today. At minimum, before any production deployment exists, define:

- **Application rollback:** redeploy the previous container image/tag; since configuration is environment-variable-driven rather than baked into the image, this should be a fast, low-risk operation once containerization exists.
- **Schema rollback:** additive-first migrations (new nullable columns/tables) minimize the need for a destructive rollback; any migration that is not purely additive should ship with an explicit, tested rollback script, not just "restore from backup" as the only option.
- **Prompt/behavior rollback:** because `conversation_policy_service.py` changes are behavior changes with production impact (see [AI_PLATFORM.md](#)), treat a bad prompt deploy with the same rollback urgency as a bad code deploy — revert the specific prompt-builder change, re-run the token-budget and content tests, and redeploy, rather than attempting a live hotfix mid-incident.
