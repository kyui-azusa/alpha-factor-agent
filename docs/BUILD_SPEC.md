# BUILD SPEC — 给 coding agent 的实现说明

本文件是**实现任务清单**,供 Claude Code / 编码智能体直接执行。按 Milestone 顺序做,每个任务都给了 **要建的文件**、**接口/函数签名** 和 **验收标准**。做完一个再做下一个;每个 Milestone 结束跑一次对应 `tests/`。

> 项目背景见 `../README.md`。核心原则:**LLM 只提想法/读结果,所有数值一律由确定性代码计算**;因子只能用当期可得信息(防 look-ahead)。

---

## 通用约定

- Python 3.10+,代码放 `src/` 下,包结构见 README。
- 配置集中在 `src/config.py`(路径、频率、股票池、成本假设、样本区间)。
- 所有涉及"未来数据"的操作必须在代码里显式对齐:因子在 T 日用的数据,发布日期必须 ≤ T。
- 每个模块写对应单测放 `tests/`,用 pytest。
- 不要在回测里调用 LLM。

---

## Milestone 0 — 配置与数据契约

**建文件**
- `src/config.py`:全局配置(dataclass 或 pydantic)。字段:`freq`, `universe`, `start_date`, `end_date`, `train_end`, `signal_time`, `fundamental_availability_time_col`, `cost_bps`(单边成本,bps), `data_dir`, `results_dir`。
- `docs/DATA_SCHEMA.md`:定义输入数据表结构(先写契约,数据后填)。至少三张表:
  - `prices`: `date, code, open, high, low, close, vol, amount, adj_factor`
  - `fundamentals`: `code, report_period, ann_date, ann_time?, <财务字段...>`(`ann_time` 仅接受经来源认证的精确发布时间)
  - `universe`: `date, code`(历史成分股,防幸存者偏差)

**验收**:`from src.config import CONFIG` 可导入;`DATA_SCHEMA.md` 明确每列含义和 dtype。

---

## Milestone 1 — 数据管线(`src/utils`)

**建文件**
- `src/utils/data_loader.py`
  - `load_prices() -> pd.DataFrame`
  - `load_fundamentals() -> pd.DataFrame`
  - `load_universe() -> pd.DataFrame`
  - `get_forward_returns(prices, periods=(1,5,20)) -> pd.DataFrame`  # 未来收益,MultiIndex[date,code]
- `src/utils/align.py`
  - `pit_merge(prices, fundamentals, *, signal_time, availability_time_col) -> pd.DataFrame`  # point-in-time 合并:每个 (date,code) 只用 signal_time 前已可用的最新财报;缺发布时间保守延至下一交易日
  - `winsorize(s, lower=0.01, upper=0.99)`,`zscore(s)`,`neutralize(factor, industry, mktcap)`  # 去极值/标准化/行业市值中性化

**验收**
- `tests/test_align.py`:覆盖交易日盘前/盘中/盘后、非交易日与缺少精确发布时间,断言 `pit_merge` **不会**把发布时间晚于 signal_time 的记录并进来,且缺时间记录下一交易日才可用(防 look-ahead 的核心测试)。
- 能对样例数据产出干净的 `data/processed/panel.parquet`。

---

## Milestone 2 — 因子引擎 + 基线因子(`src/factors`)

**建文件**
- `src/factors/engine.py`
  - `class FactorExpr`:把一个因子定义为**可执行表达式 + 元数据**。字段:`name, expression(str), economic_rationale(str), fields_used(list), formula`。
  - `def evaluate(expr: FactorExpr, panel: pd.DataFrame) -> pd.Series`  # 返回 MultiIndex[date,code] 的因子值
  - 表达式引擎:支持基础算子(加减乘除、rank、ts_mean、ts_std、delay、delta、cross-section rank),用受限 eval 或自建 AST,**禁止任意代码执行**。
- `src/factors/baseline.py`:实现 5 个基线因子并注册。
  - value(如 EP/BP)、quality(如 ROE)、momentum(如过去 20 日收益)、volatility(如 20 日波动率取负)、liquidity(如换手率取负)。

**验收**
- `tests/test_factors.py`:每个基线因子能算出非空 Series,无未来数据泄漏(只用 delay≥1 或当期已披露字段)。

---

## Milestone 3 — 回测模块(纯代码,无 LLM)(`src/backtest`)

**建文件**
- `src/backtest/metrics.py`
  - `rank_ic(factor, fwd_ret) -> pd.Series`(逐日 Rank IC)
  - `ic_ir(ic_series) -> float`
  - `quantile_returns(factor, fwd_ret, n=10) -> pd.DataFrame`(分组收益)
  - `long_short_return(quantile_ret) -> pd.Series`
  - `turnover(factor, n=10) -> pd.Series`
- `src/backtest/runner.py`
  - `def backtest(expr, panel, fwd_ret, cfg) -> dict`  # 一站式:样本外划分 → 算 IC/ICIR/分组/换手/成本后收益
  - **样本外划分**:严格按日期滚动,`train_end` 之后为样本外;禁止随机打乱。
  - 成本后收益 = 多空收益 − `turnover * cost_bps`。
- `src/backtest/report.py`
  - `def to_report(result: dict, path)`  # 存 JSON + 生成简易图(IC 累计、分组收益、净值)到 `results/reports/`

**验收**
- `tests/test_backtest.py`:用一个"未来收益本身"当因子,断言 IC≈1(理智检查);用随机因子,断言样本外 IC≈0。
- 跑一个基线因子,`results/reports/` 出报告(JSON+图)。

---

## Milestone 4 — LLM 封装(`src/llm`)

**建文件**
- `src/llm/client.py`
  - `class LLMClient`:统一接口,`generate(prompt, system=None) -> str`。
  - 支持两种后端可切换:`api`(OpenAI 兼容)/ `local`(transformers 本地模型如 Qwen)。后端由 `src/config.py` 或环境变量决定。
  - **省 token**:限制 max_tokens;缓存相同 prompt 的响应到 `data/cache/llm/`(哈希 prompt 做 key)。
- `src/llm/prompts.py`:集中放 prompt 模板(生成/校验/反馈三类),用字符串常量,便于版本管理。

**验收**:`tests/test_llm.py` 用 mock 后端,断言缓存命中不重复调用。

---

## Milestone 5 — 三个 Agent + 闭环(`src/agents`)

**建文件**
- `src/agents/generate.py`
  - `def propose_factors(existing_factors, field_dict, n=5) -> list[FactorExpr]`
  - LLM 根据经济假设产出候选因子;**输出必须是结构化的**(name/expression/economic_rationale/fields_used),用 JSON 解析,解析失败则重试。
- `src/agents/validate.py`
  - `def validate(expr: FactorExpr, field_dict) -> tuple[bool, str]`
  - 规则层(确定性):字段是否存在、表达式能否解析、是否用了未来数据(检查有没有 delay 缺失)。
  - LLM 层:判断与已有因子是否**语义重复**;最终 pass 需两层都过。
- `src/agents/feedback.py`
  - `def refine(expr, backtest_result) -> FactorExpr | None`  # 据回测结果让 LLM 改进因子
- `src/agents/loop.py`
  - `def run_loop(rounds=3, per_round=5)`  # 生成→校验→回测→反馈 的完整闭环;每轮把通过且有效的因子存到 `results/factors/`,并追加到因子库供下轮去重。

**验收**
- `tests/test_agents.py`:mock LLM,断言无效因子(用未来数据)被 validate 挡下;断言闭环能跑完 1 轮并落盘。
- `python -m src.agents.loop` 能端到端跑通,`results/factors/` 出一批带经济解释的候选因子 + 各自回测指标。

---

## Milestone 6 — 汇总与可解释性

**建文件**
- `src/report_factors.py`:把 `results/factors/` 里所有候选因子汇总成一张表(name、IC、ICIR、换手、成本后收益、与基线相关性、经济解释),导出 `results/reports/factor_summary.csv` 和一个 Markdown 卡片集。

**验收**:一张排序好的因子汇总表 + 每个因子一页"经济解释卡片"。

---

## 执行顺序总结

M0 配置契约 → M1 数据管线 → M2 因子引擎+基线 → M3 回测(纯代码) → M4 LLM封装 → M5 三Agent闭环 → M6 汇总。

**先把 M1–M3 做扎实(不涉及 LLM),这是全系统的"可信底座";M4–M5 才引入 LLM。** 没有可靠回测,LLM 生成再多因子也没意义。
