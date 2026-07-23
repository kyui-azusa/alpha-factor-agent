# Local Development Plan

Updated: 2026-07-23 18:35 +0800

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

### P1 Backtest Credibility

These make the numerical results more defensible once correctness is intact.

| Issues | Workstream | Why it matters | Suggested first step |
|---|---|---|---|
| #11 | Walk-forward OOS evaluation | Reduces dependence on one train/test split and supports robustness discussion. | Extend backtest runner/report with rolling or expanding windows, then summarize pass rate and worst window. |
| #12 | Trading feasibility constraints | A-share stop/limit/liquidity constraints can make paper returns unrealizable. | Add optional constraints to portfolio construction/reporting; keep ideal and feasible results side by side. |
| #20 | Re-skin factor detection and promotion policy | Avoids promoting near-duplicate factors that pass IC by minor variation. | Extend novelty checks beyond strict correlation and document promotion rules. |

### P2 Agent Generation Quality

These improve the LLM side without letting it control numerical claims.

| Issues | Workstream | Why it matters | Suggested first step |
|---|---|---|---|
| #14, #16, #19 | A-share knowledge base and factor hypothesis cards | Prevents black-box formula generation and separates broad hypotheses from directly backtestable factors. | Define a lightweight hypothesis card schema and field/source references before changing prompts. |
| #18 | Missing-value handling handbook | Keeps LLM proposals aware of dirty data through deterministic rules rather than ad hoc fills. | Add a field policy document or schema extension for null, negative PE, stale fundamentals, and cross-section eligibility. |
| #6 | Market-state/regime discussion | Useful, but likely belongs in limitations or future work unless implemented carefully. | Decide whether to document as limitation or add a bounded regime tag that does not leak test outcomes. |

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

## Claim Ledger

Keep this table short and current. One row can cover a grouped workstream when the implementation naturally closes multiple issues.

| Issues | Workstream | Priority | Status | Owner | Claimed at | Expires at | Notes |
|---|---|---:|---|---|---|---|---|
| #81 | Chat research clues | P0 | claimed | Codex factor-workbench task | 2026-07-23 18:35 +0800 | 2026-07-23 19:35 +0800 | The static clue-to-`ResearchRequest` route is implemented on `codex/factor-workbench`; genuine multi-turn clarification and runtime candidate generation remain open. Verified in browser at desktop and 390 x 844 mobile viewports. |
| #82 | Explainable candidate workbench | P0 | done | Codex factor-workbench task | 2026-07-23 15:31 +0800 | 2026-07-23 16:31 +0800 | Implemented an offline deterministic workbench with materials, controls, provenance, rejection reasons, availability states, and static evidence. Verified: `pytest tests/test_panel_export.py -q`; `cd panel && pnpm type-check`; `pnpm exec eslint . --cache`; `pnpm build-only`; browser desktop/mobile checks. #70/#78 remain open for runtime enforcement. |
| #7, #15 | PIT field availability and look-ahead proof | P0 | done | Codex current task | 2026-07-22 16:08 +0800 | 2026-07-22 17:08 +0800 | Implemented deterministic field availability metadata, validate/backtest enforcement, PIT-safe mktcap provenance, docs/paper limitations, and tests. Verified: `pytest tests/test_align.py tests/test_backtest.py tests/test_agents.py tests/test_factors.py -q`; `pytest -q`. |
| #10 | Expression engine whitelist and complexity limits | P0 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | Added deterministic expression safety checks and focused tests. Closed upstream with completion note on 2026-07-22. |
| #8 | Synthetic-vs-real report labeling | P0 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | Added visible `data_mode`/source metadata in reports and tests. Closed upstream with completion note on 2026-07-22. |
| #11 | Walk-forward OOS evaluation | P1 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | Added chronological walk-forward output and report summary. Closed upstream with completion note on 2026-07-22. |
| #12 | Trading feasibility constraints | P1 | open |  |  |  |  |
| #20 | Re-skin factor detection and promotion policy | P1 | open |  |  |  |  |
| #14, #16, #19 | Knowledge base and hypothesis card generation | P2 | open |  |  |  | #14 and #16 closed for hypothesis-card/landing-chain scope. #19 remains open for a fuller A-share knowledge base. |
| #18 | Missing-value handling handbook | P2 | done | Codex current task | 2026-07-22 12:10 +0800 | 2026-07-22 13:10 +0800 | Added deterministic field missing policy/generation context coverage. Closed upstream with completion note on 2026-07-22. |
| #6 | Market-state/regime handling | P2 | open |  |  |  |  |
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
