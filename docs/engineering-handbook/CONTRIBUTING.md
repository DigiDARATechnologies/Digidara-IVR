# Contributing to DigiDARA

Thank you for contributing. This document covers how to propose, build, and land a change. Read [`ENGINEERING_GUIDELINES.md`](ENGINEERING_GUIDELINES.md) first — it defines the coding, security, testing, and review principles this document assumes.

## Before You Start

- Check [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md) and [`ENGINEERING_ROADMAP.md`](ENGINEERING_ROADMAP.md) — your change may already be a scoped, prioritized item there.
- If you're touching the live call path (`app/api/openai_realtime.py`, `app/api/plivo.py`, `app/services/conversation_policy_service.py`, `app/services/telephony_service.py`), read [`VOICE_PLATFORM.md`](VOICE_PLATFORM.md) and [`AI_PLATFORM.md`](AI_PLATFORM.md) first — this is the most behaviorally sensitive part of the codebase, and two real production bugs during recent engineering work were prompt-level, not code-level.
- Confirm you're modifying the active production path, not one of the retained-but-inactive legacy paths (`app/services/twilio_service.py`, `app/api/conversation_relay.py`, `app/livekit_agent/`) — see [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md)'s "Legacy Code" section if unsure.

## Branching

- Branch from the main branch for every change; do not commit directly to it.
- Name branches descriptively by what they do, not by ticket number alone (e.g., `fix/campaign-suppression-gate`, not just `fix-123`).
- Keep branches scoped to one logical change — a bug fix and an unrelated refactor belong in separate branches/PRs.

## Making a Change

1. **Identify the root cause before writing a fix.** Trace the actual code path; do not guess. If you cannot find the root cause, say so explicitly in your PR description rather than shipping a fix you're not confident addresses the real issue.
2. **Write or update a test alongside the fix**, in the same change — not as a follow-up. This project's test suite (`python -m unittest discover -s tests -q`, 102 tests as of 2026-08-05) has caught real regressions specifically because this discipline has been followed consistently; don't be the exception.
3. **Run the full suite** before opening a PR: `python -m unittest discover -s tests -q` for the backend, `tsc -b && vite build` for the frontend.
4. **If your change touches a conversational prompt** (`conversation_policy_service.py`), verify the token-budget tests still pass (`test_policy_token_budgets`, `test_static_policy_is_compact_and_enforces_short_spoken_tamil`) and, where feasible, exercise the change on a real or recorded test call in the affected language(s) — unit tests cannot catch an LLM prompt-adherence regression on their own.
5. **If your change touches suppression/do-not-call logic** (`is_suppressed` or any of its call sites), review every call site, not just the one you're changing — this is a compliance-critical path.
6. **Do not introduce speculative abstraction.** If you're building an interface or config flag "in case we need it later," stop and check [`ENGINEERING_GUIDELINES.md`](ENGINEERING_GUIDELINES.md)'s principle on this — add it when the second real need actually appears.

## Code Review

- Every PR needs at least one review before merging, with extra scrutiny (a second reviewer, or a live-test-call requirement) for changes to: authentication/authorization, suppression/DNC logic, conversational prompts, and cost-calculation formulas.
- Reviewers should verify the stated root cause against the actual diff, not just skim for style — "does this fix what the PR says it fixes" is the first review question, not the last.
- If a reviewer requests a change that removes a test, that request should be treated as a red flag requiring justification, not routine feedback.

## Testing Expectations

See [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md) for the full framework detail. In short: `unittest`, not `pytest`; database-touching functions are tested with `MagicMock`-based connection mocking; every bug fix ships with a test.

## Documentation

- If your change introduces a new architectural decision (a new tradeoff, not just an implementation detail), add an entry to [`ARCHITECTURE_DECISION_RECORD.md`](ARCHITECTURE_DECISION_RECORD.md) following its existing format (Decision, Reason, Tradeoffs, Alternative considered, Future review trigger, Status).
- If your change closes an item in [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md) or [`ENGINEERING_ROADMAP.md`](ENGINEERING_ROADMAP.md), update that document to reflect it rather than leaving it stale.
- Code comments explain *why*, never *what* — see [`ENGINEERING_GUIDELINES.md`](ENGINEERING_GUIDELINES.md) Documentation Standards.
- Update [`CHANGELOG.md`](CHANGELOG.md) for any user-visible or architecturally significant change.

## Commit and PR Messages

- Focus commit/PR descriptions on *why*, not a restatement of the diff — the diff already shows what changed.
- If you investigated something and found it was **not** actually a bug, say so in the PR/issue rather than silently closing it — this project has a track record of reporting "not actually broken" honestly (see the telephony-cost investigation in [`ARCHITECTURE_DECISION_RECORD.md`](ARCHITECTURE_DECISION_RECORD.md) ADR-006) and that practice should continue.

## What Not to Do

- Do not disable Plivo webhook signature validation (`PLIVO_VALIDATE_SIGNATURES`) outside local development, for any reason, temporarily or otherwise.
- Do not hardcode `organization_id` (or any tenant identifier). Every tenant-owned read/write must derive and enforce organization context using the established authenticated or provider-correlated path.
- Do not commit `.env`, `credentials.json`, or any file containing real secrets or real customer phone numbers/PII.
- Do not add a new telephony/AI provider integration without checking whether it belongs behind the existing provider-abstraction pattern (`app/services/telephony/`) rather than being called directly from orchestration code.
- Do not merge a prompt change without running it past the token-budget tests and, ideally, a real test call.
