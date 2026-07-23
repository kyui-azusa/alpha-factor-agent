# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**AI金融研学实训营 · AI篇 主题四** — 可解释 Alpha 因子生成智能体。

**研究问题(已收窄,见 ADR-0022):当结构化数据已经公开了同一事件的关键数字时,LLM 读文本还能多告诉我们什么?**
检验场是 A 股业绩预告(2015–2021)。可证伪形式:LLM 从预告正文提取的语义特征,相对聚源已有的结构化字段
(幅度 / 类型 / 区间),是否具有**增量**的横截面预测力。

**阴性结果同样是完整结论** —— 项目的资产是那套裁决装置(确定性回测 + PIT 对齐 + 白名单算子 + 方法依赖图),
不是某个因子。系统敢于否决自己提出的假设,正是它可信的证据。

## 铁律(正确性约束,不可违反)

1. **回测里绝不调用 LLM。** LLM 只负责"提想法/读结果",所有数值一律由确定性代码计算。这是防线,不是优化建议。
2. **防 look-ahead:** 因子在 T 日只能用 `ann_date ≤ T` 的数据。`pit_merge`(point-in-time 合并)是核心,必须有对应单测。财报用公告日 `ann_date` 对齐,不是报告期 `report_period`。
3. **样本外划分按日期滚动**(`train_end` 之后为样本外),**禁止随机打乱**。
4. 每个 Milestone 写 pytest,过了再进下一个 Milestone。
5. **省 token:** LLM 调用要缓存(哈希 prompt 存 `data/cache/llm/`)、限 `max_tokens`;能用确定性规则判断的就别用 LLM。

## 命令

```bash
# 环境
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 测试(每个 Milestone 收尾都要跑)
pytest                              # 全部
pytest tests/test_align.py          # 单个文件(防 look-ahead 的核心测试)
pytest tests/test_align.py::test_pit_merge_excludes_future -v   # 单个用例

# 端到端闭环(M5 之后)
python -m src.agents.loop           # 生成→校验→回测→反馈,结果落 results/factors/
```

无 lint/format 工具配置;保持与现有代码风格一致即可。

## 架构大图

四步闭环,**只有回测那步不碰 LLM**:

```
生成(LLM) → 校验(规则+LLM) → 回测(纯代码,无 LLM) → 反馈(LLM) → 回到生成
```

数据从 `data/raw` → `data/processed`(清洗对齐后的 `panel.parquet`)→ `data/cache`(因子/LLM 中间结果)逐层流动。

`src/` 包职责,以及跨文件才能看懂的关键契约:

- **`src/config.py`** — 全局配置集中地(`freq`, `universe`, `start_date`, `end_date`, `train_end`, `cost_bps`, 路径)。所有模块从这里取参数,不要散落硬编码。
- **`src/utils/`** — 数据管线。`data_loader.py` 加载三张表并算前向收益;`align.py` 的 `pit_merge` 是防泄漏的关键,还有 `winsorize`/`zscore`/`neutralize`(行业市值中性化)。
- **`src/factors/`** — `engine.py` 定义 `FactorExpr`(表达式 + 经济解释 + 用到的字段等元数据)和受限表达式求值器(**禁止任意代码执行**,只允许 rank/ts_mean/delay/delta 等白名单算子);`baseline.py` 是 5 个基线因子(价值/质量/动量/波动率/流动性)。
- **`src/backtest/`** — 纯代码评价层。`metrics.py`(Rank IC、ICIR、分组收益、多空、换手)、`runner.py`(一站式回测,含样本外划分和成本后收益 = 多空收益 − turnover×cost_bps)、`report.py`(出 JSON + 图)。
- **`src/llm/`** — `client.py` 统一 `LLMClient.generate()`,后端可切换(默认 OpenAI 兼容 API,见 ADR-0013;测试用 mock);`prompts.py` 集中模板。
- **`src/agents/`** — `generate.py`/`validate.py`/`feedback.py` 三个 Agent + `loop.py` 闭环。校验分两层:确定性规则层(字段存在、表达式可解析、是否缺 delay)先过,LLM 语义查重后过,两层都过才 pass。LLM 输出必须是结构化 JSON,解析失败重试。

数据表契约(三张):`prices`(含 `adj_factor` 复权)、`fundamentals`(**`ann_date` 用于时间对齐**)、`universe`(历史成分股,防幸存者偏差)。详见 `docs/DATA_SCHEMA.md`。

## 执行顺序(按此推进)

M0 配置+数据契约 → M1 数据管线 → M2 因子引擎+基线 → M3 回测(纯代码)→ M4 LLM 封装 → M5 三 Agent 闭环 → M6 汇总可解释性。

**先把 M0–M3 做扎实(不涉及 LLM),这是全系统的"可信底座";M4–M5 才引入 LLM。** 五天冲刺版:M0–M3 必须真实且有测试,M4–M5 可轻量或按需 mock,M6 出答辩/论文材料。

## 关键文档(改方案前先读)

- **实现清单(主要看这个,含每个 Milestone 的文件/函数签名/验收标准):`docs/BUILD_SPEC.md`**
- 总览与架构:`README.md`
- 数据结构契约:`docs/DATA_SCHEMA.md`(M0 时创建)
- 共享术语与**已定决策:`CONTEXT.md` + `docs/adr/`**。这些是已接受的 ADR,不要推翻(如 0011 聚源为核心数据、0012 无聚源时用合成数据验证工程正确性、0013 LLM 后端选型)。

## 现状

目录骨架已建好,`src/` 下各包目前只有空 `__init__.py`。从 M0 开始写。`AGENTS.md` 是本文件的精简版;若改动铁律部分,两者需同步。
