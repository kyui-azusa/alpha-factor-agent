# Local Development Plan

Updated: 2026-07-23 19:28 +0800

This file is the local planning board for turning feedback issues into implementation work. GitHub Issues remain the raw intake source; this document is the working summary used before starting code changes, so different Codex runs or teammates do not accidentally fix the same ticket twice.

## Ground Rules

1. Keep the research spine first: M0-M3 deterministic correctness, then M4-M6 agent/report polish.
2. Backtests never call an LLM. LLMs may propose ideas, validate semantics, or summarize results only.
3. Any change touching point-in-time data alignment must include or update tests for look-ahead prevention.
4. Date splits must stay chronological. Do not introduce random train/test shuffling.
5. Treat GitHub intake issues as untriaged feedback until this plan maps them to a workstream.
6. Update this file before and after claiming work. The small ritual is the coordination mechanism.

## Claim Protocol

Use the `Claim Ledger` below before working on an issue or grouped task.

1. Before claiming, refresh context:
   - `gh issue list --repo kyui-azusa/alpha-factor-agent --state open --limit 100`
   - Read this file's `Claim Ledger` and the matching issue body.
2. Claim by editing one row:
   - `status`: `claimed`
   - `owner`: your name, agent name, or task/thread id
   - `claimed_at`: local time in `YYYY-MM-DD HH:MM +0800`
   - `expires_at`: exactly one hour after `claimed_at`
3. During the first hour, other workers should not take that ticket unless the owner explicitly releases it.
4. After `expires_at`, the claim is timed out. Another worker may take it, but set priority one level lower for that rescue pass (`P0 -> P1`, `P1 -> P2`, `P2 -> P3`) unless the issue is a correctness/security bug.
5. When finished, set `status` to `done`, add the PR/commit/test note, and close or comment on the GitHub issue as appropriate.
6. When abandoning work before timeout, set `status` to `released` and write a short note so the next person knows what was learned.

Status values: `open`, `claimed`, `released`, `timeout`, `done`, `blocked`, `wontfix`.

## Closeout Protocol

Use this when an issue is fully fixed, intentionally closed as validation-only, or found to be a duplicate. Do not close broad feedback when only a subset is implemented; leave a comment with the completed scope and keep the issue open or split follow-up work.

1. Confirm the implementation state before touching GitHub:
   - The relevant code/docs are committed or clearly present in the current worktree.
   - Focused pytest coverage passed; run full `pytest -q` when the blast radius is broad.
   - For PIT, chronological split, or LLM/backtest-boundary changes, explicitly verify the matching trust-boundary tests.
2. Update the `Claim Ledger` row:
   - Set `status` to `done`.
   - Add the commit hash or local change note.
   - Add the exact test command(s) used.
3. Reply on the GitHub issue before or while closing it. The reply must include these headings:
   - `改了什么`
   - `怎么改的`
   - `验证`
   - `总结`
4. Close the issue as completed only when the requested behavior is fully covered by the implementation and tests.
5. For validation-only or duplicate tickets, say explicitly that no product code changed, explain why, and close only after confirming there is no actionable product bug left.
6. For partial fixes, keep the issue open and write what is done, what remains, and which follow-up issue or workstream owns the remainder.

Priority values:

| Local priority | Meaning |
|---|---|
| P0 | Correctness blocker or trust boundary. Do first. |
| P1 | High-value project capability needed for credible defense. |
| P2 | Useful feature or documentation that improves clarity and polish. |
| P3 | Low-value, duplicate, test-only, or timed-out rescue work. |

## Current Workstreams

### P0 Research Workbench

These turn the static research panel from a result browser into an honest, inspectable factor-generation surface.

| Issues | Workstream | Why it matters | Suggested first step |
|---|---|---|---|
| #81, #82 | Chat research clues and explainable candidate workbench | Users need to see how a natural-language clue becomes a bounded candidate pool, including rejected and unavailable candidates. | Add a deterministic `ResearchRequest` preview and a static workbench with materials, generation controls, provenance, validation, and evidence states. |
| #70, #78 | Research contract and fail-closed preflight | The workbench must not imply that an incomplete or unsupported request can run. | Model the contract and blockers in the static panel; keep real confirmation, persistence, and run enforcement in the runtime workstream. |

Scope note: the current panel remains an offline static demonstration under ADR-0023. It may preview the
`ResearchRequest` and preflight schemas, but it must not claim that runtime APIs, durable state, or live backtests
exist. Issues #70 and #78 stay open until those enforcement paths are implemented and tested outside the panel.

### P0 Trust And Correctness

These protect the main claim that the system is deterministic, point-in-time, and auditable.

| Issues | Workstream | Why it matters | Suggested first step |
|---|---|---|---|
| #7, #15 | PIT field availability and look-ahead proof | The most important correctness boundary in the project. #15 also challenges the paper's current proof strength. | Audit `pit_merge`, factor evaluation paths, and report/paper wording; add tests for bypass and metadata coverage where feasible. |
| #10 | Expression engine whitelist and complexity limits | Prevents LLM output from becoming arbitrary code or unstable formulas. | Inspect `src/factors/engine.py`; add structured validation errors and tests for unknown fields/operators/window/depth. |
| #8 | Synthetic-vs-real report labeling | Prevents engineering validation from being mistaken for market evidence. | Add `data_mode` and source metadata to manifest/report outputs and tests. |
| #84 | Development feedback vs sealed OOS evidence | Prevents final out-of-sample results from becoming optimization inputs for later factor generations. | Add typed feedback provenance, allow only bounded development diagnostics into refinement, and record OOS results as terminal evidence. |

### P1 Backtest Credibility

These make the numerical results more defensible once correctness is intact.

| Issues | Workstream | Why it matters | Suggested first step |
|---|---|---|---|
| #11 | Walk-forward OOS evaluation | Reduces dependence on one train/test split and supports robustness discussion. | Extend backtest runner/report with rolling or expanding windows, then summarize pass rate and worst window. |
| #12 | Trading feasibility constraints | A-share stop/limit/liquidity constraints can make paper returns unrealizable. | Add optional constraints to portfolio construction/reporting; keep ideal and feasible results side by side. |
| #20 | Re-skin factor detection and promotion policy | Avoids promoting near-duplicate factors that pass IC by minor variation. | Extend novelty checks beyond strict correlation and document promotion rules. |
| #32 | Detailed A-share execution costs | A single turnover fee cannot represent sell-side tax, slippage, market impact, and borrow costs. | Produce a reconciled daily component ledger and integrate it with feasible target weights from #12. |

### P1 Defense Demonstration

This workstream is user-directed and has no GitHub issue. It is tracked here rather than being assigned a fabricated issue number.

| Source | Workstream | Why it matters | Scope and acceptance |
|---|---|---|---|
| User-directed | Event announcement -> market reaction research panel | Turns the research question into a defense-ready, inspectable demonstration without putting numerical work or secrets in a browser service. | Independent `panel/` Vue app; build-time adjusted market/event/factor JSON; P0/P1/P2 and offline presets; optional user-configured LLM only maps natural language to existing view parameters; `pnpm build` + offline preview; desktop and 390x844 checks; original platform links to `/panel/` without code or backend coupling. |

### P2 Agent Generation Quality

These improve the LLM side without letting it control numerical claims.

| Issues | Workstream | Why it matters | Suggested first step |
|---|---|---|---|
| #14, #16, #19 | A-share knowledge base and factor hypothesis cards | Prevents black-box formula generation and separates broad hypotheses from directly backtestable factors. | Define a lightweight hypothesis card schema and field/source references before changing prompts. |
| #18 | Missing-value handling handbook | Keeps LLM proposals aware of dirty data through deterministic rules rather than ad hoc fills. | Add a field policy document or schema extension for null, negative PE, stale fundamentals, and cross-section eligibility. |
| #6 | Market-state/regime discussion | Useful, but likely belongs in limitations or future work unless implemented carefully. | Decide whether to document as limitation or add a bounded regime tag that does not leak test outcomes. |
| #24 | Temperature validity/novelty sweep | Makes the generation randomness trade-off measurable instead of anecdotal. | Sweep a fixed grid and persist validity, novelty, uniqueness, and Pareto-frontier results. |

### P2 Factor Ideas And Explainability

These are useful candidates or reporting polish after the pipeline is stable.

| Issues | Workstream | Why it matters | Suggested first step |
|---|---|---|---|
| #9 | Standard factor explanation cards | Supports paper, defense, and review of accepted candidates. | Reuse existing report JSON and candidate JSON to render a compact card. |
| #13, #17 | Candidate factor ideas: cash-flow yield and delevered ROE | Plausible A-share factor hypotheses, but should enter through the normal candidate pipeline. | Encode as hypothesis cards first; only backtest through deterministic engine after field availability is clear. |

### P3 Housekeeping

| Issues | Workstream | Why it matters | Suggested first step |
|---|---|---|---|
| #5 | Intake test tickets | These confirm the issue system works and do not need product work. #2 was closed as validation-only on 2026-07-22. | Close or mark as validation-only after confirming no attached bug remains. |

## M7 Direction: One Falsifiable Increment Experiment

The next phase stops expanding generic alpha-agent capabilities. It executes one frozen research question end to end: whether performance-forecast announcement text adds predictive value beyond the structured forecast fields on the same point-in-time, out-of-sample events.

| Order | Issue | Concrete implementation | Intended effect | Test gate |
|---:|---|---|---|---|
| 1 | #35 | Export and normalize the 2015-2021 `LC_PerformanceForecast` event table with stable IDs and next-trading-day availability. | Establish one PIT event fact table shared by every later stage. | Duplicate, holiday, future-event, report-period, negative-base, stable-ID, and schema-failure fixtures. |
| 2a | #36 | Freeze a walk-forward structured-only feature/model pipeline with per-window transforms and manifests. | Create the one allowed control group without text leakage or OOS refitting. | Chronological split, train-only fit, text-column rejection, unknown category, missing semantics, and replay determinism. |
| 2b | #37 | Convert announcement text to versioned semantic fields through an offline, hash-keyed LLM cache. | Turn nondeterministic text reading into a frozen data-production step outside backtesting. | Cache key/version changes, strict schema, bounded retry, offline miss failure, replay, redaction, and no-LLM architecture boundary. |
| 3 | #38 | Compare structured-only with structured-plus-text on exactly matched event/date/universe/config keys. | Make text increment directly falsifiable instead of reporting a standalone text factor. | Key/config mismatch rejection, zero-text zero delta, injected-signal recovery, chronological OOS, and offline execution. |
| 4a | #39 | Run Newey-West inference on the paired daily Rank IC delta series with horizon-derived lag. | Prevent overlapping returns from creating false precision. | Hand-calculated HAC, AR(1), zero/positive delta, lag boundary, NaN alignment, short sample, and direct-difference checks. |
| 4b | #40 | Report coverage funnels, PIT neutralization, exchange/board/year/type/industry/size slices, and disclosure bias. | Distinguish genuine text increment from selection, industry, size, or exchange concentration. | Funnel conservation, mutually exclusive loss reasons, date isolation, future-industry invariance, neutral exposure, and insufficient-slice states. |
| 5 | #41 | Freeze hashes/configs in an experiment manifest and replay all deterministic artifacts offline into positive, negative, or inconclusive reports. | Make the final claim auditable and allow a valid negative result without moving the goalposts. | Manifest completeness, byte-stable replay, tamper failure, no API key/network, conclusion semantics, and sensitive-output scan. |

Dependency graph: `#35 -> (#36, #37) -> #38 -> (#39, #40) -> #41`. #36 and #37 may run in parallel; #39 and #40 may run in parallel. The primary estimand, matched sample, neutralization, horizons, execution constraints, and costs are frozen before observing the treatment result.

Final verification for the completed credibility batch: `pytest tests/test_costs.py -q` (`7 passed`), `pytest tests/test_backtest.py -q` (`9 passed`), and `pytest -q` (`90 passed in 210.72s`). `git diff --check` and `python -m json.tool knowledge/a_share/v1.json` also passed.

## Claim Ledger

Keep this table short and current. One row can cover a grouped workstream when the implementation naturally closes multiple issues.

| Issues | Workstream | Priority | Status | Owner | Claimed at | Expires at | Notes |
|---|---|---:|---|---|---|---|---|
| #42, #43, #44, #45 | Intake ticket referencing, full history list, needs-review flag, and list filters | P1 | done | Claude current task | 2026-07-23 10:40 +0800 | 2026-07-23 11:40 +0800 | Replaced the unused `related_packet` field with `related_issues` (free-text parse, max 5, written as GitHub cross-references; deliberately no in-site reply hierarchy); fixed the hardcoded `per_page=20` that hid every ticket before #13 and switched receipt lookup to one repo-level comments query; added the `needs_review` flag (`待审核` label + body statement, either one counts); added state/type/submitter filters plus 只看待审核 / 收起回复 toggles and an 8-item preview with 展开全部. Verified: `pytest tests/test_intake_service.py -q` (14 passed); `python platform/build.py`; real-repo `list_issues()` returns all 32 tickets in 2.8s with receipts resolved; browser checks of every filter, the cite toggle, and both themes against real ticket data. Not yet deployed — needs `systemctl restart alpha-intake` plus the static upload. |
| user-directed | Event announcement -> market reaction research panel | P1 | done | Codex current task | 2026-07-23 01:48 +0800 | 2026-07-23 02:48 +0800 | Completed independent static `panel/`, build-time adjusted JSON export, P0/P1/P2 views, offline Agent presets, optional browser-direct model configuration, and the independent `/panel/` platform entry. Verified: `python platform/build.py`; `pnpm type-check`; `pnpm lint`; `pnpm build`; `pytest -q tests/test_panel_export.py tests/test_intake_service.py` (19 passed); `pytest -q` (78 passed). Browser checks passed at desktop and 390x844 with no horizontal overflow, no console errors, local-only panel resources, and all three offline presets working. A local OpenAI-compatible mock also verified free-input factor and portfolio actions; clearing model configuration disabled free input while preserving offline presets. |
| #69 | Fundamental freshness and coverage audit | P1 | done | Codex fundamental-freshness-audit task | 2026-07-23 19:51 +0800 | 2026-07-23 20:51 +0800 | Implemented field-specific stale thresholds, mutually exclusive exclusion reasons, date/industry coverage summaries, stable persisted audit evidence, and PF-013/PF-014 integration. Verified: `pytest tests/test_fundamental_quality.py tests/test_align.py tests/test_research_preflight.py tests/test_agents.py -q` (50 passed); `pytest -q` (104 passed); `python -m compileall -q src tests`; `git diff --check`. |
| #67 | Announcement-time PIT availability and audit | P0 | done | Codex pit-availability-audit task | 2026-07-23 19:34 +0800 | 2026-07-23 20:34 +0800 | Implemented explicit signal-time PIT merge, certified exact publication timestamps, midnight/date-only next-trading-day fallback, fail-closed timestamp validation, audit counts, and schema contract. Verified: `pytest tests/test_align.py tests/test_agents.py tests/test_backtest.py tests/test_research_preflight.py -q` (49 passed); `pytest -q` (96 passed); `python -m compileall -q src tests`; `git diff --check`. |
| #83 | Traceable generation cache | P1 | done | Codex run-state-cache task | 2026-07-23 19:08 +0800 | 2026-07-23 20:08 +0800 | Added atomic content-addressed generation records and stable candidate lineage. Verified: focused pytest 21 passed; full pytest 94 passed; compileall and diff check passed. |
| #79 | Persistent run state and recovery core | P0 | released | Codex run-state-cache task | 2026-07-23 19:08 +0800 | 2026-07-23 20:08 +0800 | Backend core completed: SQLite state/stage/candidate history, cancel, partial completion, stable errors, restart persistence, idempotent retry, and child runs for changed inputs. Issue remains open for runtime service and panel history/control integration; released after backend PR so that UI/API work can proceed on the correct branch. |
| #70, #78 | Research request contract and deterministic preflight | P0 | done | Codex research-contract-preflight task | 2026-07-23 18:44 +0800 | 2026-07-23 19:44 +0800 | Implemented immutable confirmed contracts, fail-closed capability evidence, versioned preflight reports, integrity-checked execution permits, and Agent generation gating. Verified: `pytest tests/test_research_contract.py tests/test_research_preflight.py tests/test_agents.py tests/test_pipeline.py -q` (36 passed); `pytest -q` (87 passed); `python -m compileall -q src tests`; `git diff --check`. |
| #81 | Chat research clues | P0 | claimed | Codex factor-workbench task | 2026-07-23 18:35 +0800 | 2026-07-23 19:35 +0800 | The static clue-to-`ResearchRequest` route is implemented on `codex/factor-workbench`; genuine multi-turn clarification and runtime candidate generation remain open. Verified in browser at desktop and 390 x 844 mobile viewports. |
| #82 | Explainable candidate workbench | P0 | done | Codex factor-workbench task | 2026-07-23 15:31 +0800 | 2026-07-23 16:31 +0800 | Implemented an offline deterministic workbench with materials, controls, provenance, rejection reasons, availability states, and static evidence. Verified: `pytest tests/test_panel_export.py -q`; `cd panel && pnpm type-check`; `pnpm exec eslint . --cache`; `pnpm build-only`; browser desktop/mobile checks. #70/#78 remain open for runtime enforcement. |
| #7, #15 | PIT field availability and look-ahead proof | P0 | done | Codex current task | 2026-07-22 16:08 +0800 | 2026-07-22 17:08 +0800 | Implemented deterministic field availability metadata, validate/backtest enforcement, PIT-safe mktcap provenance, docs/paper limitations, and tests. Verified: `pytest tests/test_align.py tests/test_backtest.py tests/test_agents.py tests/test_factors.py -q`; `pytest -q`. |
| #10 | Expression engine whitelist and complexity limits | P0 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | Added deterministic expression safety checks and focused tests. Closed upstream with completion note on 2026-07-22. |
| #8 | Synthetic-vs-real report labeling | P0 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | Added visible `data_mode`/source metadata in reports and tests. Closed upstream with completion note on 2026-07-22. |
| #84 | Development feedback vs sealed OOS evidence | P0 | done | Codex task 019f8ea8 | 2026-07-23 19:09 +0800 | 2026-07-23 20:09 +0800 | Implemented typed provenance and per-source prompt allowlists, categorical dev diagnostics, terminal OOS evidence/failure reasons, and report audit state on `codex/oos-feedback-boundary`. Verified: `pytest tests/test_align.py tests/test_backtest.py tests/test_agent_parsing.py tests/test_agents.py tests/test_factors.py -q` (41 passed); `pytest -q` (71 passed); `python -m compileall -q src tests`; `git diff --check`. |
| #11 | Walk-forward OOS evaluation | P1 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | Added chronological walk-forward output and report summary. Closed upstream with completion note on 2026-07-22. |
| #12 | Trading feasibility constraints | P1 | done | Codex remaining-ticket task | 2026-07-23 | 2026-07-23 | Commit `35e55b3`: order-level suspended/limit-direction checks, shifted ADV capacity, participation caps, partial fills, and ideal/tradable/executable results. Integrated with detailed costs in `45b1d98`. Verified: `pytest tests/test_backtest.py -q` (`9 passed`). |
| #30 | Layered robustness evaluation | P1 | done | Codex remaining-ticket task | 2026-07-23 | 2026-07-23 | Commit `35e55b3`: market regime, industry, size, liquidity/universe, rebalance frequency, forward horizon, cost grid, and explicit robustness labels. Verified: `pytest tests/test_backtest.py -q` (`9 passed`). |
| #20 | Re-skin factor detection and promotion policy | P1 | done | Codex remaining-ticket task | 2026-07-23 | 2026-07-23 | Added deterministic expression fingerprints, candidate/library and candidate/candidate signal checks, rolling convergence, post-backtest Rank IC/return-path similarity, explicit promotion decisions, and reversible demotion. Verified: `pytest tests/test_novelty.py tests/test_temperature.py tests/test_agents.py -q`; `pytest -q`. |
| #32 | Detailed A-share execution costs | P1 | done | Codex remaining-ticket task | 2026-07-23 | 2026-07-23 | Commits `001fdf1` and `45b1d98`: signed turnover, commission, date-aware sell-only stamp duty, slippage, nonlinear participation impact, short-borrow accrual, turnover-weighted coverage, and a reconciled ledger applied to #12 feasible holdings. Corrected the issue's unit error: `1 per mille = 10 bps`, not 100 bps. Verified: `pytest tests/test_costs.py -q` (`7 passed`) and `pytest tests/test_backtest.py -q` (`9 passed`). |
| #14, #16, #19 | Knowledge base and hypothesis card generation | P2 | done | Codex remaining-ticket task | 2026-07-23 | 2026-07-23 | Added a versioned, source-traceable A-share knowledge catalog, runtime field intersection, citation requirements, and fail-closed validation for unregistered backtest fields. |
| #18 | Missing-value handling handbook | P2 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | Added deterministic field missing policy/generation context coverage. Closed upstream with completion note on 2026-07-22. |
| #6 | Market-state/regime handling | P2 | done | Codex remaining-ticket task | 2026-07-23 | 2026-07-23 | Added deterministic T-1 market regimes and a bounded `where(regime_*, on_true, on_false)` operator; future-invariance, branch, metadata, and AST-safety tests cover the boundary. |
| #24 | Temperature validity/novelty sweep | P2 | done | Codex remaining-ticket task | 2026-07-23 | 2026-07-23 | Added a deterministic sweep runner with requested/proposed/parse-failure counts, rule validity, strict novelty, warning acceptance, uniqueness, Pareto flags, and JSON/CSV artifacts. Verified: `pytest tests/test_temperature.py -q`; `pytest -q`. |
| #9 | Standard factor explanation cards | P2 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | Added factor card output in backtest reports. Closed upstream with completion note on 2026-07-22. |
| #13, #17 | Candidate factor ideas | P2 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | Registered cash-flow yield and delevered ROE as explainable seed/candidate factors. Closed upstream with completion note on 2026-07-22. |
| #5 | Intake validation tickets | P3 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | #2 and #5 closed as validation-only on 2026-07-22; no product code change required. |

## Claim Examples

Fresh claim:

| Issues | Workstream | Priority | Status | Owner | Claimed at | Expires at | Notes |
|---|---|---:|---|---|---|---|---|
| #10 | Expression engine whitelist and complexity limits | P0 | claimed | Codex task abc123 | 2026-07-22 14:45 +0800 | 2026-07-22 15:45 +0800 | Reading `src/factors/engine.py`; tests planned in `tests/test_factors.py`. |

Timed-out rescue:

| Issues | Workstream | Priority | Status | Owner | Claimed at | Expires at | Notes |
|---|---|---:|---|---|---|---|---|
| #10 | Expression engine whitelist and complexity limits | P1 | claimed | Codex task def456 | 2026-07-22 16:10 +0800 | 2026-07-22 17:10 +0800 | Previous claim expired; rescue priority lowered from P0 to P1. |

## Sync Checklist

Use this quick pass at the start and end of each work block.

1. Pull latest local branch if collaborating through git.
2. Refresh GitHub open issues with `gh issue list`.
3. Update `Claim Ledger` before editing code.
4. Run the focused pytest set for the workstream.
5. Write completion notes here and on the GitHub issue.
6. If a ticket is closed upstream, mark its row `done` or remove it during the next cleanup pass.
