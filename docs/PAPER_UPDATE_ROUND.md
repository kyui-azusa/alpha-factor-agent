# 真实数据库接入后一轮论文更新流程

这份流程用于“已经连上聚源/SQL Server 后，怎样把论文从 synthetic 工程验证更新到真实数据初步实证”。原则是先落证据，再改正文：没有真实三表和确定性回测结果前，不把论文写成“已完成真实实证”。

## 1. 让当前进程拿到数据库连接

如果连接信息已经在另一个终端里，Codex 这边未必能继承到。推荐写到本地忽略文件：

```bash
cp config/mssql.env.example config/mssql.env
# 编辑 config/mssql.env，填入 ALPHA_MSSQL_HOST / USER / PASSWORD / DATABASE 等
python scripts/mssql_tool.py --env-file config/mssql.env doctor
```

`doctor` 输出里密码会脱敏，但仍不要把真实主机、用户名或库名写进论文和公开仓库。

## 2. 先保存库表字段快照

```bash
python scripts/mssql_tool.py --env-file config/mssql.env snapshot \
  --output-dir data/metadata/mssql/latest \
  --row-counts
```

如果数据库很大或权限有限，先不加 `--row-counts`，或者用 `--schema dbo` 限定 schema。快照产物是 `databases.csv`、`tables.csv`、`columns.csv`、`manifest.json`，用于离线字段映射。

生成候选表排序，先让机器把最像行情、财务、股票池的表挑出来：

```bash
python scripts/mssql_find_fields.py \
  --metadata-dir data/metadata/mssql/latest
```

输出 `data/metadata/mssql/latest/field_candidates.md`。

## 3. 映射三张项目 raw 表

论文和回测只认 `docs/DATA_SCHEMA.md` 里的三张表：

| output | 必须覆盖的核心字段 |
|---|---|
| `data/raw/prices.csv` | `date, code, open, high, low, close, vol, amount, adj_factor`，最好还有 `mktcap, industry` |
| `data/raw/fundamentals.csv` | `code, report_period, ann_date` 以及财务/估值字段；`ann_date` 必须是真实公告日 |
| `data/raw/universe.csv` | `date, code`，最好是历史股票池/历史可交易集合 |

先用 `field_candidates.md` 和快照搜索表名、字段名：行情看 `Quote/Price/Daily/Trading/复权`，财务看 `Balance/Income/CashFlow/Indicator/公告日`，股票池看 `Index/Constituent/StockList/Listed/ST/Suspend`。确认后再写导出 SQL，比如：

```bash
python scripts/mssql_tool.py --env-file config/mssql.env export \
  --sql-file sql/export_prices.sql \
  --output data/raw/prices.csv
python scripts/mssql_tool.py --env-file config/mssql.env export \
  --sql-file sql/export_fundamentals.sql \
  --output data/raw/fundamentals.csv
python scripts/mssql_tool.py --env-file config/mssql.env export \
  --sql-file sql/export_universe.sql \
  --output data/raw/universe.csv
```

## 4. 跑一轮确定性结果并生成论文片段

三张 raw 表落地后，现有 pipeline 会自动替代 synthetic fallback：

```bash
python scripts/paper_update_round.py --run-pipeline
```

输出目录：`results/paper_update/latest/`。

| file | 用途 |
|---|---|
| `status.md` | 检查三张 raw 表是否存在、行数、代码数、日期范围，以及是否仍会 fallback 到 synthetic。 |
| `latex_tables.tex` | 可放进论文实验章节的表格片段。 |
| `manifest.json` | 本轮更新的机器可读状态。 |

如果 `status.md` 仍显示 `synthetic fallback would be used by the pipeline`，说明论文正文只能保留“合成数据工程验证”，不能写真实数据结论。

## 5. 更新论文正文的顺序

当 `status.md` 确认三张 raw 表都存在，且 `baseline_summary.csv` / `factor_summary.csv` 已由真实数据重跑后，再更新：

1. `paper/main.tex` 摘要：把“真实聚源数据接入前”改成“基于聚源数据完成初步样本外实证”，但要说明样本区间和股票池边界。
2. `paper/main.tex` 实验章节：新增真实数据设置、样本区间、股票数、观测数、成本假设。
3. `paper/main.tex` 表格：用 `results/paper_update/latest/latex_tables.tex` 中的真实数据表替代 synthetic 示例表，或把 synthetic 表降级为工程验证附录。
4. 讨论章节：把“下一阶段接入真实数据”改为“下一阶段扩展稳健性检验/字段覆盖/更长样本”。
5. 结论：只写确定性回测已经支持的结论，不写“发现稳定 alpha”这类超过证据的话。

## 6. 更新前的最低验收

```bash
pytest
python scripts/paper_update_round.py
```

论文中的所有数字必须能从 `results/reports/` 或 `results/paper_update/latest/` 追溯回来；回测路径仍然不能调用 LLM。
