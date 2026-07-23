# Alpha Factor Agent — 可解释 Alpha 因子生成智能体

> AI金融研学实训营 · AI篇 主题四
> **研究问题:当结构化数据已经公开了同一事件的关键数字时,LLM 读文本还能多告诉我们什么?**
> 检验场:A 股业绩预告(2015–2021)

一套"LLM 提假设 → 程序验证 → 反馈迭代"的闭环系统:让 LLM 根据经济含义提出可解释的候选因子,再由确定性代码自动检查重复/未来数据、做统一样本外检验。重点不是挖历史高收益,而是让**每个因子都有明确计算逻辑和经济解释**。

**为什么是这个问题。** 业绩预告的幅度、类型、区间在聚源里都是现成的结构化字段,任何量化团队都能直接用;LLM 唯一可能的增量在正文的归因语义里。这让"为什么非要用 LLM"从一句辩解变成一个**可量化、有对照组、可证伪**的检验:增量存在,说明文本确有未被定价的信息;增量不存在,说明市场对该类事件的文本信息已充分定价 —— **两个方向都是结论**。

项目真正的资产是那套裁决装置(确定性回测 + 点时间对齐 + 白名单算子 + 方法依赖图),不是某个因子。详见 ADR-0022。

---

## 想看进展 / 提反馈

研究过程沉淀的想法流在 **[alpha.cihua.run](https://alpha.cihua.run/)**。

- **在网页上直接提**:打开 <https://alpha.cihua.run/#submit> 填表单即可 —— **无需 GitHub 账号**,系统会自动同步成一条 Issue。
- **有 GitHub 账号**:直接 [新建 Issue](../../issues/new?template=feedback.yml)。
- **本地开发排期 / 认领表**:见 [`docs/DEV_PLAN.md`](docs/DEV_PLAN.md)。开工前先看 Claim Ledger,避免重复处理同一工单。

请勿在工单里粘贴敏感数据。

---

## 系统架构

```
                    ┌─────────────────────────────┐
                    │   因子库 & 经济含义提示       │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
         ┌─────────►│  1. 因子生成 Agent (LLM)     │  产出:因子表达式 + 经济解释
         │          └──────────────┬──────────────┘
         │                         │
         │          ┌──────────────▼──────────────┐
         │          │  2. 校验 Agent (LLM+规则)    │  查:重复? look-ahead? 可计算?
         │          └──────────────┬──────────────┘
         │                通过     │
         │          ┌──────────────▼──────────────┐
         │          │  3. 回测模块 (纯代码, 不用LLM)│  算:IC/ICIR/换手/成本后收益
         │          └──────────────┬──────────────┘
         │                         │
         │          ┌──────────────▼──────────────┐
         └──────────┤  4. 反馈 Agent (LLM)         │  据回测结果改进因子
                    └─────────────────────────────┘
```

**省 token 设计**:LLM 只在生成/校验/反馈三步调用(短文本);回测全部走本地代码,不烧 token。

---

## Agent 分工(输入 → 输出)

| Agent | 输入 | 输出 | 用什么 |
|---|---|---|---|
| 因子生成 | 已有因子库、字段字典、经济假设 | 候选因子表达式 + 经济解释文本 | LLM(可本地 Qwen / 付费 API) |
| 校验 | 候选因子、字段可得性表 | 是否重复 / 是否用未来数据 / 能否计算 | LLM 判断 + 确定性规则复核 |
| 回测 | 通过校验的因子、行情&财务数据 | IC、ICIR、分组收益、换手率、成本后收益 | 纯 Python(pandas/numpy),**无 LLM** |
| 反馈 | 回测结果 + 因子 | 改进建议 / 新候选 | LLM |

> 关键防线:LLM 生成的任何**数值结论一律由确定性程序复核**,LLM 只负责"提想法"和"读结果",不负责算数。

---

## 数据

- **来源**:聚源数据库(财务报表、估值、交易、行业、公司行为、复权价)。
- **范围**:A 股横截面;先用日频。
- **时间边界**:候选因子**只能用当期可得信息**,严格保留字段来源与计算公式,防 look-ahead。
- 目录:`data/raw`(原始)→ `data/processed`(清洗对齐)→ `data/cache`(因子中间结果)。

---

## 评价指标

统一对所有候选因子计算,**不能只按历史收益筛选**:

- **Rank IC / ICIR**(样本外)
- **分组收益**(多空组合、单调性)
- **换手率** 及 **交易成本后收益**
- **与已有因子的相关性**(增量价值)
- 稳健性:多个市场状态 / 滚动样本外

基线因子:价值、质量、动量、波动率、流动性(等权多因子)。

---

## 每周排期(约 5–6 周)

| 周 | 目标 | 产出 |
|---|---|---|
| W1 | 数据管线 + 基线因子库 | `data/processed` 就绪,5 个基线因子可算 IC |
| W2 | 回测模块(纯代码) | `src/backtest` 完成,基线因子回测报告 |
| W3 | 因子生成 + 校验 Agent | 能自动产出并过滤候选因子 |
| W4 | 反馈闭环 + 批量实验 | 完整闭环跑通,产出一批候选因子 |
| W5 | 稳健性检验 + 可解释性整理 | 样本外/多状态检验,因子经济解释卡片 |
| W6 | 论文/汇报 + 复现打包 | 报告 + 可复现代码 |

---

## 目录结构

```
alpha-factor-agent/
├── data/            raw / processed / cache
├── src/
│   ├── agents/      generate / validate / feedback
│   ├── backtest/    IC、分组、成本、样本外划分
│   ├── factors/     基线因子 + 因子表达式引擎
│   ├── llm/         模型调用封装(本地/API 可切换)
│   └── utils/       数据加载、时间对齐、字段字典
├── notebooks/       探索与可视化
├── results/         factors / reports / logs
├── tests/
└── docs/
```

## 快速开始

```bash
cd alpha-factor-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 当前可运行交付

当前仓库已经实现 `docs/BUILD_SPEC.md` 中的 M0-M6 初版链路。默认没有真实聚源数据时,系统会使用 deterministic synthetic data 做工程验证;这些结果只用于证明流程正确,不代表真实市场结论。

一键运行完整可复现实验:

```bash
python -m src --rounds 1 --per-round 2
```

只运行确定性基线因子,跳过 LLM/Agent:

```bash
python -m src --skip-agent
```

运行后主要产物:

| 路径 | 内容 |
|---|---|
| `data/processed/panel.parquet` 或 `panel.pkl` | 点时间对齐后的研究面板 |
| `results/reports/baseline_summary.csv` | 5 个基线因子的样本外回测摘要 |
| `results/factors/*.json` | Agent 通过校验并回测后的候选因子 |
| `results/reports/factor_summary.csv` | 候选因子汇总,含 IC/ICIR/换手/成本后收益/基线相关性 |
| `results/reports/*/report.json` 与 `summary.png` | 单因子详细报告与图表 |
| `results/run_manifest.json` | 本次运行摘要 |

验证:

```bash
pytest -q
```

## 学校内网 SQL Server 接入

已提供可复用探库/导出脚本 `scripts/mssql_tool.py`,真实连接信息通过环境变量或本地 `config/mssql.env` 传入,不要写进仓库。

```bash
cp config/mssql.env.example config/mssql.env
python scripts/mssql_tool.py --env-file config/mssql.env doctor
python scripts/mssql_tool.py --env-file config/mssql.env databases
python scripts/mssql_tool.py --env-file config/mssql.env tables
python scripts/mssql_tool.py --env-file config/mssql.env snapshot --output-dir data/metadata/mssql/latest
```

完整说明见 `docs/JUYUAN_SQLSERVER.md`。确认聚源实际库表和字段后,再把正式导出 SQL 映射到 `data/raw/prices.csv`、`data/raw/fundamentals.csv`、`data/raw/universe.csv`。

## 模型后端

默认后端是 `mock`,便于无网络、无 API key 时复现实验结构。真实模型只参与候选生成、语义校验和反馈,回测永远不调用 LLM。

OpenAI-compatible API:

```bash
export ALPHA_AGENT_LLM_BACKEND=api
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=https://api.openai.com/v1  # 可选
export ALPHA_AGENT_LLM_MODEL=gpt-4.1-mini
python -m src --rounds 1 --per-round 3
```

本地 OpenAI-compatible 服务,例如 vLLM/Ollama 代理:

```bash
export ALPHA_AGENT_LLM_BACKEND=local
export ALPHA_AGENT_LOCAL_BASE_URL=http://localhost:8000/v1
export ALPHA_AGENT_LOCAL_API_KEY=EMPTY
export ALPHA_AGENT_LLM_MODEL=Qwen2.5-7B-Instruct
python -m src --rounds 1 --per-round 3
```

模型调参优先级:先调 prompt、JSON 输出约束、temperature/max_tokens 和规则校验;只有在候选输出长期不稳定且积累了足够高质量样本后,才考虑 LoRA 微调。详见 `docs/MODEL_STRATEGY.md`。

## 参考文献

- McLean & Pontiff (2016), *Does Academic Research Destroy Stock Return Predictability?*, JF
- Kou et al. (2025), *Automate Strategy Finding with LLM in Quant Investment*, EMNLP Findings
- Huang et al. (2026), *AlphaFormer: End-to-End Symbolic Regression of Alpha Factors with Transformers*, PMLR
- Gu, Kelly & Xiu (2020), *Empirical Asset Pricing via Machine Learning*, RFS(滚动样本外划分范例)
