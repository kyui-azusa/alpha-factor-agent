# 0013 — OpenAI-compatible LLM backend first

日期:2026-07-20
状态:已接受

The five-day build will default to the user's available Codex/OpenAI-compatible API for LLM-assisted idea generation, semantic validation, and feedback, with MiniMax kept as an optional fallback or text-generation provider and mock backends used in tests. The project will not spend core time deploying a local model, and the backtest path remains deterministic code with no LLM calls.
