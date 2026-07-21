GENERATE_FACTORS_SYSTEM = """You propose explainable A-share alpha factor hypotheses. Return JSON only.
Numerical claims are forbidden. Backtests are performed by deterministic Python code."""

GENERATE_FACTORS_PROMPT = """Existing factors:
{existing_factors}

Available fields:
{field_dict}

Propose {n} candidate factors as a JSON array. Each item must contain:
name, expression, economic_rationale, fields_used.
Use only safe expression functions: rank, cs_rank, ts_mean, ts_std, delay, delta, safe_div, signed_log.
Do not use fwd_ret_* or future returns."""

VALIDATE_SEMANTIC_PROMPT = """Existing factors:
{existing_factors}

Candidate:
{candidate}

Is the candidate semantically duplicated with an existing factor? Return JSON: {{"duplicate": true/false, "reason": "..."}}."""

FEEDBACK_PROMPT = """Factor:
{factor}

Backtest summary:
{summary}

Suggest one improved candidate factor as JSON with name, expression, economic_rationale, fields_used, or return null if no responsible improvement is justified."""
