# DigiDARA — Testing Strategy

## Framework Note (Read This First)

This project uses Python's built-in **`unittest`**, run via `python -m unittest discover -s tests -q`. `pytest` appears in some historical documentation and is a common assumption for Python projects, but it is **not installed** in the project's virtual environment — do not write `pytest`-only fixtures/features (e.g., `pytest.fixture`, `pytest.mark.parametrize`) without first confirming `pytest` has actually been added as a dependency. As of 2026-08-05 the suite stands at **102 passing tests**.

## Unit Testing

Unit tests cover pure logic and service functions with database access mocked via `unittest.mock.MagicMock`/`patch`:

- **Conversation intent/end-of-call classification** (`tests/test_conversation_end.py`): regex-pattern coverage for explicit and implicit end-of-call phrasings in both English and Tamil, including negative-question forms ("won't you cut the call") and confirming unrelated questions do *not* falsely trigger an end-of-call classification.
- **Conversation policy** (`tests/test_conversation_policy_service.py`, `tests/test_tamil_conversation_service.py`): token-budget ceilings on static prompt text, verified via an `estimate_prompt_tokens` helper — a prompt edit that grows a builder's output past its budget must be reworded to fit, not exempted.
- **Plivo protocol/XML generation** (`tests/test_plivo_migration.py`): `build_answer_xml` and `build_language_prompt_xml` output shape assertions (recording/stream attributes present, no provider `<Speak>` in the main flow, the language-menu's `<GetDigits>`/`<Play>` structure and its Record/Stream fallback), plus stream-token generation/validation, status-code mapping, and Plivo V3 signature validation (mocked at the `plivo.utils` module boundary).
- **Campaign automation** (`tests/test_campaign_automation.py`): `customer_service.upsert_customer` (create vs. update path, phone validation, language normalization), `google_sheets_service.update_sheet_status` (delegates correctly to `update_sheet_feedback`), and `telephony_service.is_suppressed` (per-customer flag, org-scoped phone-hash list, and the "no phone available" edge case) — all added when these functions were found to not exist at all, or (for `is_suppressed`) newly introduced.

**Database-mocking pattern:** service functions that take a live `conn`/`db` connection are tested by constructing a `MagicMock()` connection whose `cursor().fetchone`/`fetchall` are configured with `side_effect` or `return_value` sequences matching the expected query order (see `IsSuppressedTests._conn_with()` in `test_campaign_automation.py` for the canonical example). This pattern did not exist in the codebase before the campaign-automation fix and is now the established convention for new DB-touching unit tests — follow it rather than inventing a new mocking approach per test file.

## Integration Testing

There is no dedicated integration-test suite (e.g., tests that spin up a real MySQL instance and exercise multiple service layers together) in the repository today. Ad hoc integration verification during development has instead taken the form of direct Python scripts run against the live local database and live provider APIs (e.g., verifying `estimated_telephony_cost_usd` against Plivo's live `get_call()` CDR response across every completed call, or verifying header-normalization output against a real sheet's column names) — useful for one-off diagnosis, but not repeatable or CI-friendly. Formalizing a small integration suite (a disposable test-schema database, seeded fixtures, real service-layer calls without mocking the DB) is a reasonable near-term addition once CI exists (see [ENGINEERING_ROADMAP.md](#) Epic B) — scope it to the highest-risk flows first: call placement + suppression enforcement, and campaign-sheet upsert + queue advancement.

## End-to-End (E2E) Testing

No automated E2E suite exists (e.g., a scripted test that places a real or simulated call end-to-end and asserts on recorded transcript/outcome). Verification today is manual live-call testing — which is exactly how two real conversational bugs were found and fixed during this engineering pass (the English-hangup dead-code path, and the Tamil-prompt over-broad English-switch instruction) — but manual-only E2E coverage means these classes of bug are only caught when someone happens to test that specific path. A minimal automated E2E smoke test — placing a call against a test number, confirming the DTMF menu is reachable, confirming a known end-of-call phrase in each language actually terminates the call within an expected time window — would close a real gap; see [ENGINEERING_ROADMAP.md](#) Epic C.

## Performance Testing

No load/performance testing exists today (e.g., how many concurrent Realtime WebSocket bridges the backend can sustain, or how bulk-campaign dialing behaves against a sheet with hundreds of rows under real network latency). This has not yet been a priority because the system has not yet operated at a volume where it would matter, but it becomes a real prerequisite before Epic D's "run a real campaign against a full-size lead sheet" roadmap item, and should be scoped then rather than speculatively now.

## Security Testing

Security regression coverage now asserts that every private HTTP route requires a valid admin dependency, account lockout blocks the post-threshold attempt even when the correct password is supplied, and representative direct and indirect tenant-owned data paths use the authenticated organization and deny a foreign call detail. `test_tenant_database_integration.py` is an opt-in real-MySQL test that creates two temporary workspaces with the same email, proves workspace-specific authentication and customer/campaign isolation, then deletes its fixtures; it is skipped in the normal environment-independent suite unless `RUN_DB_INTEGRATION_TESTS=1`. The highest-value remaining additions are full HTTP-surface two-tenant integration coverage and an end-to-end webhook-signature-tampering rejection test.

## Regression Testing

The full `unittest discover` run *is* the regression suite — there is no separate "regression" test tier. The discipline that keeps it meaningful: every behavioral bug fix in this codebase has shipped with a new or updated test in the same change, so a future change that reintroduces a previously-fixed bug (e.g., re-gating the English hangup path behind a language check, or reverting the transcription-cost formula to a flat rate) should fail an existing test rather than silently regressing. Maintaining this discipline going forward — not skipping the "add a test" step under time pressure — is the single highest-leverage testing practice already established in this codebase and the one most worth explicitly preserving.

## Recommended Near-Term Additions (Priority Order)

1. CI running the existing suite on every change (currently run manually) — see [ENGINEERING_ROADMAP.md](#) Epic B.
2. A minimal automated E2E smoke test for the DTMF language menu and end-of-call tool-call path in both languages.
3. Cross-tenant access-denial tests, added alongside the organization-scoping enforcement work in Epic A — write the test *with* the fix, per this codebase's own established discipline, not after.
4. A small integration-test tier against a disposable test database for the call-placement + suppression, and campaign-sheet upsert + queue-advancement flows.
