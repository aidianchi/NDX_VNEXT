# NEXT_STEPS 1–4 Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development task-by-task. This plan is executed inline in the current workspace; the user explicitly forbids commits and pushes.

**Goal:** Close the real remaining gaps in `NEXT_STEPS.md` directions 1–4 without weakening evidence authority, point-in-time discipline, or publish gates; assess direction 5 without speculative surgery.

**Architecture:** Preserve strict current contracts and add narrowly scoped compatibility only for recognizable legacy failure payloads. Make recomputation inputs explicit in collector artifacts, keep the recomputation book independent, attach field-level authority to weak indicators, and move Golden Pit evidence attribution to deterministic predicate-to-source mapping. Reporter work consumes artifacts without feeding any reader-exit state back into L1–L5.

**Tech Stack:** Python 3.12, pytest, Pydantic, self-contained HTML/CSS/JS.

---

### Task 1: Legacy snapshot replay compatibility

**Files:**
- Modify: `src/data_evidence.py`
- Test: `tests/test_data_evidence_contract.py`

- [ ] Add a regression test using the old L3 shape: `availability=available`, all observation fields null, and an explicit `Failed to calculate` note.
- [ ] Run the test and confirm it fails with `available_without_meaningful_value`.
- [ ] Normalize only contract-less legacy failure payloads to `availability=unavailable`, retaining the failure note and an audit anomaly.
- [ ] Verify the regression plus all data-evidence/backtest tests pass; prove a new-contract meaningless `available` payload still hard-blocks.

### Task 2: Independent recomputation raw-input coverage

**Files:**
- Modify: `src/tools_L1.py`
- Modify: `src/tools_L2.py`
- Modify: `src/tools_L5.py`
- Modify: `src/recompute_belt.py`
- Test: `tests/test_recompute_belt.py`
- Test: focused producer tests under `tests/test_l1_*`, `tests/test_l2_*`, and `tests/test_l5_*`

- [ ] Add failing tests requiring dated raw series for long-window percentile/momentum producers and full PIT-truncated OHLCV for the deterministic L5 snapshot.
- [ ] Add failing recomputation tests for 1y/5y/10y percentiles, 1-day velocity/acceleration, SMA50–200, and the existing L5 technical fields.
- [ ] Embed bounded, dated raw observations in the producer payloads without importing pipeline calculation code into `recompute_belt.py`.
- [ ] Implement independent stdlib recomputations and explicit formula/tolerance notes; unavailable indicators remain honestly unavailable rather than counted as missing raw.
- [ ] Run focused tests and compare the fresh report’s `unrecomputable_missing_raw` count with the recorded 61-field baseline.

### Task 3: Eight weak-authority indicators

**Files:**
- Modify: `src/tools_L1.py`
- Modify: `src/tools_L2.py`
- Modify: `src/tools_L4.py`
- Test: `tests/test_l4_data_authority.py` or a new focused authority test file
- Test: `tests/test_run_review.py`

- [ ] Write parameterized failing tests for `get_vix`, `get_vxn`, `get_copper_gold_ratio`, `get_hyg_momentum`, `get_xly_xlp_ratio`, `get_crowdedness_dashboard`, `get_vxn_vix_ratio`, and `get_cnn_fear_greed_index`.
- [ ] Attach payload-level `data_quality.metric_authority` and `downgrade_rules` aligned with `deep_research_canon.py`.
- [ ] Verify runtime evidence passports expose the rules and Run Review no longer reports these eight as missing downgrade discipline.

### Task 4: Earnings-expectation decision

**Files:**
- Inspect: `src/tools_L4.py`
- Test: `tests/test_l4_external_valuation_sources.py`
- Test: `tests/test_l4_forward_earnings_quality.py`

- [ ] Re-run HoM interface/current-tail/freshness/history/percentile tests.
- [ ] Do not implement top-15 forward-EPS aggregation or revive FMP/Finnhub unless evidence disproves the documented unit, coverage, and authority objections.
- [ ] Record the decision and remaining invalidation condition in `NEXT_STEPS.md` / `WORK_LOG.md`.

### Task 5: Personal-decision wiring without invented thresholds

**Files:**
- Modify: `src/state_ledger.py`
- Modify: `src/agent_analysis/orchestrator.py`
- Modify: `config/user_decision_profile.json`
- Test: `tests/test_vnext_orchestrator.py`
- Test: `tests/test_state_ledger.py`

- [ ] Add failing tests that predicate-backed conditions cite only the source refs for their own state variables.
- [ ] Add a stable state-variable-to-evidence-ref mapping and use it for profile condition refs/falsifiers; claim-type unions remain fallback only for legacy conditions without predicates.
- [ ] Keep tracked and local profiles threshold-free until the user confirms values; add explicit empty schema slots and validation/audit text so missing thresholds cannot silently become active disciplines.
- [ ] Verify no personal amounts enter tracked files or rendered reports.

### Task 6: Output experience completion

**Files:**
- Modify: `src/agent_analysis/vnext_reporter.py`
- Modify: report CSS under `src/agent_analysis/report_styles/`
- Test: `tests/test_vnext_reporter.py`
- Verify: `tests/test_research_console.py`, `tests/test_control_service.py`, `tests/test_open_research_console.py`

- [ ] Replace the report-layer shared-ref workaround’s need by consuming item-specific upstream refs; preserve safe rendering for old artifacts.
- [ ] Add accessible hover/focus/click glossary explanations for HY OAS, ADX, MACD and other recurring technical terms, keeping the visible report concise.
- [ ] Add an explicit snapshot audit block showing source filename/reference, collection time, effective date, and mode, with honest placeholders when metadata is absent.
- [ ] Verify the already-implemented simple launcher against its plan and mark the stale roadmap item complete.

### Task 7: Direction 5 assessment and final verification

**Files:**
- Modify only if a low-risk, independently testable debt item is discovered.
- Update: `NEXT_STEPS.md`
- Update: `WORK_LOG.md`

- [ ] Do not split giant files or alter the deterministic inquiry stub without an approved design and a focused behavioral test.
- [ ] Run focused suites, then `.venv/bin/python -m pytest -q` fresh.
- [ ] Run a read-only reviewer over the final diff; fix all Critical and Important findings.
- [ ] Re-run final verification and inspect `git diff --check` plus `git status --short`.
- [ ] Do not commit or push.
