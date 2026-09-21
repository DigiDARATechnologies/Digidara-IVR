# DigiDARA — Implementation Checklist

Each Epic from [ENGINEERING_ROADMAP.md](#) is broken down here into concrete stories with tasks, acceptance criteria, verification steps, and a rollback plan. Work through checklists top-to-bottom within an epic; epics themselves follow the suggested implementation order in the roadmap.

---

## Epic A — Tenancy & Access Control Hardening

### Story A1: Derive `organization_id` from request context, not a hardcoded value

- [x] Task: Identify every active API/service call site that wrote or assumed organization `1`.
- [x] Task: Resolve `organization_id` from the authenticated user's database row and require it to match the signed JWT claim.
- [x] Task: Update `issue_token()` to embed `organization_id` in the JWT claims.
- [x] Task: Update active write paths to use the authenticated or provider-correlated organization instead of a literal tenant ID.
- **Acceptance criteria:** No literal `organization_id = 1` (or any other hardcoded tenant ID) remains in `app/api/*.py` or `app/services/*.py`; a new user created via any path is correctly attributed to their actual organization.
- **Verification:** A test creating two organizations and one admin user per organization, asserting each user's created resources carry the correct, distinct `organization_id`.
- **Rollback:** Revert the JWT-claim and call-site changes together as one unit; this is an additive schema-compatible change (no column changes), so rollback is a pure code revert with no data migration to undo.

### Story A2: Enforce account lockout

- [x] Task: Increment `app_users.failed_login_attempts` on each failed `/auth/login` attempt.
- [x] Task: Set `locked_until` after a defined threshold (currently 3 failures for 60 seconds; configurable and bounded; planned production policy is 5 failures for 15 minutes).
- [x] Task: Check `locked_until` before attempting password verification; return a clear, non-enumerating error if locked.
- [x] Task: Reset `failed_login_attempts` to 0 and clear `locked_until` on successful login.
- **Acceptance criteria:** After the configured number of consecutive failed attempts, further attempts are rejected until `locked_until` passes, regardless of whether the correct password is eventually supplied within the lock window.
- **Verification:** A test simulating N failed logins asserts the (N+1)th attempt is rejected even with the correct password, and that a successful login before the threshold resets the counter.
- **Rollback:** Purely additive logic in the existing `login()` function; revert the code change, no data cleanup required (leftover non-zero `failed_login_attempts` values are harmless).

### Story A3: Organization-scoped authorization on every endpoint

- [x] Task: Audit routes in `app/api/*.py` that read or write tenant-scoped tables.
- [x] Task: Extend `current_admin` to return the database-backed organization and reject a JWT/database organization mismatch.
- [x] Task: Scope the audited customer, campaign, call, insight, chat, lead, and admin-user queries by that organization.
- **Acceptance criteria:** A valid token for organization A cannot read or modify any row belonging to organization B, across every audited endpoint.
- **Verification:** `tests/test_tenant_isolation.py` verifies token binding, principal mismatch rejection, organization inheritance, scoped service SQL, cross-tenant call-detail denial, analytics scoping, and indirect chat/lead/memory paths. Add full database-backed two-organization integration coverage before commercial tenant onboarding.
- **Rollback:** Endpoint-by-endpoint code revert is safe; no schema change involved.

### Story A3b: Open workspace registration and selection

- [x] Task: Add public organization creation with a unique workspace slug and no operator key.
- [x] Task: Create or claim an empty organization and assign its first administrator in one transaction, with an organization-scoped audit event.
- [x] Task: Add workspace ID to sign-in and remember it alongside the email and lockout deadline.
- [x] Task: Scope account lookup by workspace before password verification while retaining a safe compatibility response for an omitted ambiguous workspace.
- [x] Task: Add unit coverage and an opt-in real-MySQL test that creates two temporary organizations sharing one admin email, verifies isolation, and cleans up its records.
- **Acceptance criteria:** A user can register Organization B without direct SQL or an operator secret; each organization can authenticate the same email using its own workspace ID; one organization cannot retrieve the other's customer or campaign records.
- **Verification:** `RUN_DB_INTEGRATION_TESTS=1 python -m unittest discover -s tests -p "test_tenant_database_integration.py" -v` passes against the configured local MySQL database, and the normal suite safely skips this environment-dependent test.
- **Remaining limitation:** Registration is intentionally open for the current local product phase. It is not internet-ready until email verification, rate limiting/CAPTCHA, recovery, suspension, and payment-entitlement enforcement are added. The legacy `/auth/bootstrap-admin` recovery route remains separately protected by `ADMIN_BOOTSTRAP_KEY`.

### Story A4: Role-based access control beyond binary admin

- [ ] Task: Define the actual roles the business needs (e.g., `admin`, `campaign_manager`, `counsellor`) and the permissions each requires.
- [ ] Task: Extend authorization dependencies to check the specific permission needed per endpoint, not just "is admin."
- **Acceptance criteria:** A non-admin role can perform exactly the actions it should and no others, verified per role.
- **Verification:** Per-role authorization tests covering both an allowed and a denied action for each new role.
- **Rollback:** Additive; existing admin behavior must remain unchanged as a regression check.

### Story A5: Per-tenant provider credentials via `api_credentials`

- [ ] Task: Implement encryption/decryption for `credential_ciphertext` (confirm and reuse `DATA_ENCRYPTION_KEY`, consistent with the recording-encryption mechanism).
- [ ] Task: Add read/write service functions for per-org credentials (Plivo, OpenAI, Google) with `key_version`-aware rotation support.
- [ ] Task: Migrate provider-client construction (`get_telephony_provider()`, OpenAI WebSocket connection setup) to resolve credentials per-organization instead of solely from `.env`, with `.env` remaining a fallback for a default/single-tenant deployment.
- **Acceptance criteria:** Two organizations can each configure and use their own Plivo/OpenAI credentials without interference.
- **Verification:** Integration test placing a simulated call using org-specific credentials, confirming the correct credential set was used.
- **Rollback:** Keep the `.env`-based path functioning as a fallback throughout, so this can be rolled back per-organization without a global outage.

---

## Epic B — Dependency, Build & CI Hygiene

### Story B1: Pinned dependency manifest

- [x] Task: Capture exact direct dependency versions from the known-working virtual environment.
- [x] Task: Review imports and remove accidental/transitive-only entries; hand-curate `app/requirements.txt`.
- [x] Task: Confirm a clean install from the manifest into a fresh virtual environment reproduces a working `python -m unittest discover` run (102 tests on 2026-08-05).
- **Acceptance criteria:** A fresh clone plus a fresh virtual environment plus one install command produces a working backend.
- **Verification:** CI itself (Story B2) is the ongoing verification; manually verify once before CI exists.
- **Rollback:** N/A — this is a net-additive change with no behavior to roll back.

### Story B2: CI pipeline

- [x] Task: Add a CI workflow running `python -m unittest discover -s tests -q` on every push/PR.
- [x] Task: Add a CI job running `npm ci && npm run build` for the frontend.
- [ ] Task: Require both to pass before merge.
- **Publication note:** The workflow exists locally; after it is pushed, enable GitHub branch protection so both CI jobs are required checks.
- **Acceptance criteria:** A change that breaks a test or the frontend build is blocked from merging.
- **Verification:** Intentionally introduce a failing test in a throwaway branch to confirm CI blocks it, then revert.
- **Rollback:** Disable the CI gate if it produces false positives blocking legitimate work, while the underlying cause is fixed — do not leave it permanently disabled.

---

## Epic C — Voice Platform Reliability

### Story C1: Investigate `NULL` `conversation_end_reason` on a completed Tamil call

- [ ] Task: Add targeted debug logging around every write path to `call_logs.conversation_end_reason`.
- [ ] Task: Reproduce a Tamil call ending via each known path (explicit tool call, customer hangup, provider-side hangup) and confirm the field is set correctly in each case.
- **Acceptance criteria:** Every call-ending path reliably sets `conversation_end_reason` to a non-null, accurate value.
- **Verification:** A matrix of test calls (or simulated equivalents) covering each termination path, asserting the persisted reason.
- **Rollback:** Logging-only changes are zero-risk to add/remove; any code-path fix should ship with the regression test from the matrix above.

### Story C2: Automated live-call smoke testing

- [ ] Task: Script a test call (or a simulated equivalent hitting the same webhook/WebSocket surface) covering: DTMF menu reachability, both language selections, and a known end-of-call phrase in each language.
- [ ] Task: Assert expected call-log state (`status`, `conversation_end_reason`, `language`) after each scenario.
- **Acceptance criteria:** The smoke test suite catches at minimum the two classes of live bug already found manually this pass (dead hangup path, prompt-language drift).
- **Verification:** Run the smoke suite against a deliberately-reintroduced version of one of the two known-fixed bugs, confirming it fails.
- **Rollback:** N/A — additive test tooling.

### Story C3: Tamil-script-aware `language_switch` detection

- [ ] Task: Extend the detection in `openai_realtime.py` (~line 845) to recognize Tamil-script requests to switch to English, not just the ASCII substring `"english"`.
- **Acceptance criteria:** A Tamil-script utterance explicitly requesting English is correctly classified and flips `response_language`.
- **Verification:** Unit test feeding representative Tamil-script phrasing through the detection logic.
- **Rollback:** Isolated code change; revert independently of other work.

### Story C4: Stable non-local ingress

- [ ] Task: Choose and provision a stable ingress mechanism (reverse proxy/load balancer with a real domain and managed TLS) for any staging/production environment.
- [ ] Task: Update `WEBHOOK_BASE_URL`/`PLIVO_STREAM_BASE_URL` provisioning to use the stable hostname per environment, never a Quick Tunnel outside local development.
- **Acceptance criteria:** A call placed against staging/production does not depend on any process that can silently change the public hostname.
- **Verification:** Restart the application process and confirm webhook URLs remain valid without manual `.env` intervention.
- **Rollback:** Standard infrastructure rollback for whatever ingress technology is chosen; keep the Quick Tunnel path available for local development regardless.

---

## Epic D — Campaign Automation at Real Volume

### Story D1: Per-environment Google service-account provisioning

- [ ] Task: Create a dedicated service account per environment (not a developer's personal one), scoped to Sheets/Drive access only as needed.
- [ ] Task: Document the provisioning process (create account, download key, share target sheets with the account's email as Editor) in onboarding material.
- **Acceptance criteria:** Sheet write-back works in any environment without depending on one specific developer's machine.
- **Verification:** Run a full bulk-campaign trigger in a clean environment using only the newly-provisioned credentials.
- **Rollback:** Revoke/rotate the service-account key if compromised; the public-CSV read fallback remains available regardless.

### Story D2: Real-volume campaign run

- [ ] Task: Run `/calls/run-sheet` against a full-size (hundreds-of-rows) lead sheet.
- [ ] Task: Monitor suppression-gate correctness (spot-check that every suppressed row was actually skipped and marked, not dialed), sheet-write-back latency/failure rate, and queue-advancement correctness.
- **Acceptance criteria:** The queue advances correctly through the full sheet, no suppressed lead is dialed, and sheet status accurately reflects each row's outcome by the end of the run.
- **Verification:** Post-run reconciliation comparing `call_logs` rows against the sheet's final status column, row by row.
- **Rollback:** N/A — this is a validation exercise; any bug found should be fixed and covered by a new unit test per the project's established discipline.

### Story D3: Expand recognized sheet header aliases

- [ ] Task: As real customer sheets are encountered with unrecognized header variants, add them to `normalize_headers()`.
- **Acceptance criteria:** A real customer sheet's phone/name/language/status columns are recognized without requiring the customer to rename their own spreadsheet headers.
- **Verification:** Unit test asserting the new alias maps correctly, alongside the existing header-mapping tests.
- **Rollback:** Purely additive; a new alias cannot break an existing one unless it collides, which the existing test suite would catch.

---

## Epic E — Cost & Usage Observability

### Story E1: Per-organization quota enforcement

- [ ] Task: Check `organizations.monthly_call_limit` before placing a new outbound call; reject or queue calls beyond quota.
- **Acceptance criteria:** An organization cannot exceed its configured monthly call limit.
- **Verification:** Test placing calls up to and beyond the limit, asserting rejection beyond it.
- **Rollback:** Feature-flag the enforcement initially so it can be disabled without a code revert if a quota-calculation bug is found in production.
- **Depends on:** Epic A (organization context must be reliably resolved first).

### Story E2: Scheduled telephony-cost reconciliation job

- [ ] Task: Add a periodic job re-verifying `estimated_telephony_cost_usd` against live Plivo CDR data for recently-completed calls.
- **Acceptance criteria:** Any call whose hangup-callback-time cost reconciliation was missed is caught within one job cycle.
- **Verification:** Simulate a missed hangup callback and confirm the scheduled job corrects the stored cost on its next run.
- **Rollback:** Job can be disabled independently without affecting the existing hangup-time reconciliation.

---

## Epic F — Knowledge & Conversation Quality

### Story F1: Formal prompt-change review checklist

- [ ] Task: Write a short checklist (token-budget check, live-test-call requirement, both-language verification where applicable) and require it for every `conversation_policy_service.py` change.
- **Acceptance criteria:** Every merged prompt change has an attached record of the checklist having been followed.
- **Verification:** Retroactively apply the checklist to the two known prompt-caused incidents this pass, confirming it would have caught them.
- **Rollback:** Process-only change; no code rollback applicable.

### Story F2: Automated conversation-quality evaluation

- [ ] Task: Define a small, fixed set of representative transcript scenarios per language with expected behavior (tool-call firing, language consistency, no invented facts).
- [ ] Task: Build a scoring harness that replays or evaluates against these scenarios.
- **Acceptance criteria:** The harness flags a regression when a known-bad prompt version is fed through it.
- **Verification:** Feed the harness the pre-fix version of the over-broad English-switch prompt and confirm it flags the issue.
- **Rollback:** N/A — additive tooling.

---

## Epic G — Deployment & Operations Maturity

### Story G1: Containerize the backend

- [ ] Task: Write a Dockerfile using the pinned dependency manifest (Epic B), running as non-root, fully env-var-configured.
- **Acceptance criteria:** `docker build && docker run` with an appropriate `.env` produces a working backend equivalent to the local dev setup.
- **Verification:** Run the full test suite inside the built container.
- **Rollback:** Continue running the non-containerized setup in parallel until the container is verified in a real environment.

### Story G2: Rollback strategy documentation

- [ ] Task: Document application rollback (redeploy previous image) and schema rollback (per-migration rollback script or documented manual procedure) explicitly.
- **Acceptance criteria:** A team member unfamiliar with a specific deploy can execute the documented rollback without improvising.
- **Verification:** Dry-run a rollback in a non-production environment.
- **Rollback:** N/A — this task produces the rollback plan itself.

### Story G3: Expand audit logging coverage

- [ ] Task: Add `audit_logs` writes for authentication events, suppression-list changes, customer data export/deletion, credential rotation, and campaign create/modify.
- **Acceptance criteria:** Each listed action produces a corresponding audit-log row with correct actor and organization attribution.
- **Verification:** Trigger each action in a test environment and confirm the expected audit row.
- **Rollback:** Additive logging; safe to revert per-action if a specific log point proves noisy or incorrect.

### Story G4: Enforce data retention

- [ ] Task: Build a scheduled job that purges or archives data older than `organizations.data_retention_days`, and enforces `call_logs.recording_retention_until`.
- **Acceptance criteria:** Data older than the configured retention window is actually removed/archived, not merely tagged.
- **Verification:** Run the job against fixture data with mixed ages and confirm only the correct rows are affected.
- **Rollback:** Run the job in dry-run/report-only mode initially before enabling actual deletion, to catch a misconfiguration before it destroys data.
