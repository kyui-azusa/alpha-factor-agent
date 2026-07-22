GENERATE_FACTORS_SYSTEM = """You propose explainable A-share alpha factor hypotheses. Return JSON only.
Numerical claims are forbidden. Backtests are performed by deterministic Python code.
In generation, you may only use the provided field catalog, seed factors, rules, and text priors.
Never infer real historical values, stock paths, future returns, IC, Sharpe, or out-of-sample results."""

GENERATE_FACTORS_PROMPT = """Existing factors:
{existing_factors}

Generation context:
{generation_context}

Propose {n} candidate factors as a JSON array. Each item must contain:
name, expression, economic_rationale, fields_used, and metadata.
metadata must contain: category, seed_factors, generation_method, alpha_target,
economic_mechanism, field_sources, a_share_mapping, direction, scope,
backtestable_status, status_reason, risk_exposures, validation_notes,
source_seed_factors, synthesis_method, mechanism_change, expression_version, lineage,
knowledge_citations. Every currently_backtestable candidate must cite the knowledge_source_id
for each field it uses. Use only fields present in the provided formal field_catalog.
Use one of the provided synthesis_methods and record how the expression descends from seed_factor_lineage.
Use only safe expression functions: rank, cs_rank, ts_mean, ts_std, delay, delta, safe_div, signed_log, where.
where(condition, on_true, on_false) accepts only a provided binary regime field as its condition;
comparisons and Python if expressions remain forbidden.
Do not use fwd_ret_* or future returns. If a hypothesis is not currently backtestable with the catalog,
mark backtestable_status accordingly instead of inventing fields."""

VALIDATE_SEMANTIC_PROMPT = """Existing factors:
{existing_factors}

Candidate:
{candidate}

Is the candidate semantically duplicated with an existing factor? Return JSON: {{"duplicate": true/false, "reason": "..."}}."""

FEEDBACK_PROMPT = """Factor:
{factor}

Backtest summary:
{summary}

Suggest one improved candidate factor as JSON with name, expression, economic_rationale, fields_used, metadata,
or return null if no responsible improvement is justified. Only use training-segment information in the summary."""
