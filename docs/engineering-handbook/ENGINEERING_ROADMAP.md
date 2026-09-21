# DigiDARA — Engineering Roadmap

This roadmap sequences work from the current working-prototype state toward a hardened, multi-tenant commercial product. Priorities are ordered by risk reduction first, feature breadth second — a compliance or tenancy gap in a system already handling real phone numbers is a materially different risk class than a missing analytics chart.

## How to read this document

- **Epic** — a body of related work with a shared goal.
- **Story** — a user- or system-facing outcome within an epic.
- **Priority** — P0 (blocking further growth / active risk), P1 (near-term, before scaling usage), P2 (planned, not urgent).
- **Risk** — what happens if this is left undone.
- **Timeline** — relative sizing (S = days, M = one–two weeks, L = multiple weeks), not calendar dates, since team size is not fixed in this document.

---

## Epic A — Tenancy & Access Control Hardening

**Goal:** Make the multi-tenant boundary the schema already defines actually enforced in application code, before a second organization's data ever coexists with another's.

| Story | Priority | Risk if undone | Timeline | Depends on |
|---|---|---|---|---|
| **Completed 2026-08-06:** Derive `organization_id` from the authenticated request context; remove hardcoded tenant IDs from active API/service paths | P0 | Closed for the audited authenticated data paths | M | None |
| **Completed 2026-08-06:** Enforce account lockout using the existing `failed_login_attempts`/`locked_until` columns | P0 | Closed: current three-failure/60-second policy is configurable; planned production setting is five failures/15 minutes | S | None |
| **Completed 2026-08-06:** Add organization-scoped authorization to the audited customer, campaign, call, insight, chat, lead, and admin-user reads/writes | P0 | Closed for audited tenant-owned tables; regression tests cover representative direct and indirect access paths | L | Org-context derivation above |
| **Completed 2026-08-07:** Add open workspace registration, atomic first-admin assignment, workspace-aware login, and a real-MySQL two-organization isolation test | P0 | Registration works locally; email verification, anti-abuse controls, and payment entitlements remain future work | M | Organization-scoped authorization |
| Add subscription/payment entitlements that gate calling, campaign activation, and billable operations while allowing account/workspace setup | P1 | Open registration currently grants immediate product access; commercial deployment needs server-enforced plan status and provider-webhook reconciliation | L | Billing provider decision and stable deployment |
| Expand `role_code` beyond a binary admin flag into real role-based access control, using the schema's `role_code` field as the seed | P1 | Every authenticated user is effectively an admin or nothing; no least-privilege model for counsellor-level staff | M | Above |
| Wire `api_credentials.credential_ciphertext` into actual use for per-tenant provider credentials (Plivo, OpenAI, Google) instead of a shared `.env` | P1 | Every tenant would otherwise share one set of provider credentials, which is both a security and a billing-attribution problem | M | Org-context derivation |

## Epic B — Dependency, Build & CI Hygiene

**Goal:** Make the backend's dependencies reproducible and its correctness continuously verified, closing the gap identified in ADR-010.

**Status (2026-08-05):** The two P0 stories are implemented locally and verified. GitHub branch-protection configuration remains an owner/repository setting rather than a code change.

| Story | Priority | Risk if undone | Timeline | Depends on |
|---|---|---|---|---|
| **Completed:** Pin direct backend dependencies in `app/requirements.txt` from the known-working Python 3.11 environment | P0 | Closed locally; upgrades are now deliberate and reviewable | S | None |
| **Completed:** Add GitHub Actions jobs for the backend suite and locked frontend build on every push/PR | P0 | Closed in code; branch protection must require the checks after publication | S | Pinned dependencies |
| Add a lightweight pre-commit or CI lint/format pass (backend and frontend) | P2 | Style drift accumulates; not a functional risk today | S | CI above |

## Epic C — Voice Platform Reliability

**Goal:** Close the remaining gaps in the live call flow found during this engineering pass, and prevent their recurrence class.

| Story | Priority | Risk if undone | Timeline | Depends on |
|---|---|---|---|---|
| Investigate the observed case of a completed Tamil call with `conversation_end_reason` left `NULL` despite code appearing correct — add targeted debug logging around the persistence path and reproduce | P1 | Silent gaps in call-disposition data undermine analytics and lead-status accuracy | S | None |
| Add automated live-call smoke testing (or at minimum a documented manual test script) covering both languages' end-of-call tool-call path and the DTMF language-menu path | P1 | Prompt/behavior regressions (two of which were found live during this pass) are only caught by chance manual testing today | M | None |
| Replace the ASCII-only `"english"`/`"tamil"` substring check in the `language_switch` intent branch (`openai_realtime.py` lines ~845–848) with genuine Tamil-script-aware detection | P2 | A customer explicitly asking, in Tamil words, to switch to English would be misclassified and ignored | S | None |
| Provision a stable ingress (replacing developer-local Cloudflare Quick Tunnels) for any non-local environment | P0 | Quick Tunnels are ephemeral by design; their hostname changes whenever the tunnel process restarts, which has already caused a live call-creation failure (`ValidationError` traced to a dead tunnel hostname) in this engineering pass | M | Deployment target decided (see Epic G) |

## Epic D — Campaign Automation at Real Volume

**Goal:** Prove the now-fixed bulk-calling loop under real lead volume and real Google Sheets service-account provisioning, not just unit tests and a 2–3 row throwaway sheet.

| Story | Priority | Risk if undone | Timeline | Depends on |
|---|---|---|---|---|
| Provision per-environment Google service-account credentials (not one developer's local `credentials.json`) so sheet write-back works outside a single machine | P0 | Sheet status write-back (`update_sheet_feedback`) raises immediately without credentials — the read-only public-CSV fallback cannot substitute for it | S | None |
| Run a real campaign against a full-size lead sheet and monitor: suppression-gate correctness, sheet-write-back latency/failure rate, and queue-advancement correctness under real network conditions | P1 | The 2–3 row test validates logic; it does not validate behavior at hundreds of rows or against real-world sheet header variance | M | Credentials above |
| Expand `normalize_headers()`'s recognized header aliases based on real customer sheet formats as they're encountered (the "Phone no" alias gap found and fixed this pass is unlikely to be the last) | P2 | A silently-unrecognized phone/name column causes 100% of rows in a sheet to be skipped with no obvious error | S | None |

## Epic E — Cost & Usage Observability

**Goal:** Make unit economics (cost per call, per campaign, per organization) trustworthy and actionable, building on the transcription-cost fix already shipped.

| Story | Priority | Risk if undone | Timeline | Depends on |
|---|---|---|---|---|
| Add a scheduled reconciliation job that re-verifies `estimated_telephony_cost_usd` against live Plivo CDR data periodically, not just at hangup-callback time | P2 | Retried/delayed provider callbacks are already handled at hangup time; a periodic reconciliation adds defense against any missed callback | S | None |
| Surface per-organization cost and quota (`organizations.monthly_call_limit`) enforcement, not just recording | P1 | The schema has a quota field with no enforcement today; a tenant could exceed its plan's call volume with no system response | M | Epic A (org enforcement) |
| Add cost/latency telemetry specifically for `end_call` tool-call reliability (latency from customer intent to tool invocation) | P2 | No current visibility into whether the AI-judged termination is fast/reliable in aggregate versus just anecdotally observed in test calls | S | None |

## Epic F — Knowledge & Conversation Quality

**Goal:** Grow knowledge-base coverage and add systematic conversation-quality evaluation, given that two live conversational bugs this pass were prompt-level, not code-level.

| Story | Priority | Risk if undone | Timeline | Depends on |
|---|---|---|---|---|
| Formalize the prompt-change review process from [ENGINEERING_GUIDELINES.md](#) into an actual checklist/template used for every `conversation_policy_service.py` change | P1 | Prompt regressions repeat the two live incidents already seen (over-broad English-switch instruction; assumption that Plivo could speak Tamil) | S | None |
| Add automated conversation-quality evaluation (e.g., transcript-based rubric scoring, not just cost/latency metrics) | P2 | Quality regressions are currently only caught by manual live-call review | L | None |
| Expand approved knowledge-base coverage per language beyond current course/fee/batch content | P2 | Limits how many real customer questions can be answered from approved facts rather than general model knowledge | M | None |

## Epic G — Deployment & Operations Maturity

**Goal:** Move from a single developer-operated local environment to a documented, repeatable deployment with monitoring and incident response.

| Story | Priority | Risk if undone | Timeline | Depends on |
|---|---|---|---|---|
| Containerize the backend and define a production configuration (env-driven, no hardcoded local paths) | P1 | No repeatable deployment artifact exists today | M | Pinned dependencies (Epic B) |
| Define and document a rollback strategy for both schema migrations and application deploys | P1 | No documented recovery path if a deploy or migration misbehaves | S | Containerization |
| Wire `audit_logs` coverage across all sensitive actions (currently only admin-account creation), and enforce `organizations.data_retention_days` via a scheduled job | P2 | Audit trail and data-retention are schema-ready but not operationally real yet | M | Epic A |

---

## Suggested Implementation Order

1. Complete Epic B locally: pinned dependencies and CI workflow. This is implemented; GitHub branch protection follows publication.
2. Complete Epic A's P0 local security items: private-route authentication coverage, account lockout, organization-context derivation, and organization-scoped authorization. Route authentication coverage is implemented; lockout and tenant scoping remain.
3. Complete Epic D's local credential provisioning and campaign-reliability work, including restart/failure tests and a controlled 100+ lead run.
4. Add local operational readiness from Epics E and G: structured logs, health/readiness checks, backup/restore proof, monitoring hooks, and rollback documentation.
5. Complete policy, privacy, retention, and live English/Tamil pilot acceptance checks.
6. Only after the local gates pass, provision the VPS, permanent domain/TLS, stable Plivo ingress, hosted database, and production monitoring.
7. Continue Epic F as an ongoing conversation-quality program rather than a one-time milestone.

## Milestones

- **M1 — Reproducible & Verified:** Pinned dependencies, CI workflow, clean backend install, frontend locked build, and private-route authentication coverage.
- **M2 — Tenancy-Safe:** Organization context derived everywhere, lockout enforced, per-endpoint authorization audited.
- **M3 — Proven at Volume:** A real campaign run end-to-end against a full lead sheet with provisioned credentials, suppression and write-back verified under real conditions.
- **M4 — Deployment-Ready Locally:** Health checks, structured monitoring, backup/restore, rollback, audit logging, retention, and the pilot checklist verified before infrastructure provisioning.
- **M5 — Controlled Hosted Pilot:** VPS, domain/TLS, stable ingress, managed database, production secrets, monitoring, and a signed-off pilot run.
- **M6 — Platform:** Per-tenant credentials and RBAC live; additional providers or languages are added only when backed by a real requirement.
