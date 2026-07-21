# 数据库关键元信息记录清单

这份清单用于学校内网数据库不可随时访问时的离线开发。先把数据库的库名、表名、字段名、字段类型快照下来;真实行情和财务数据可以后面再按需导出。

## 最关键的三类数据

### 1. 日频行情与复权数据 -> `prices`

用途:计算收益、动量、波动率、流动性、换手率、分组收益和回测净值。

必须找的字段:

| target column | why it matters | common source hint |
|---|---|---|
| `date` | 交易日,所有样本外切分和回测索引。 | trade date / tradingday / enddate |
| `code` | 股票代码,横截面主键。 | secu code / ticker / inner code |
| `open/high/low/close` | 日频价格,收益和波动率基础。 | adjusted price preferred |
| `vol` | 成交量,流动性因子。 | volume / turnover volume |
| `amount` | 成交额,流动性和成交约束。 | turnover value / amount |
| `adj_factor` | 复权因子,避免分红送转造成伪收益。 | adjustment factor |

强烈建议同时找:

| target column | why it matters |
|---|---|
| `mktcap` | 市值中性化、规模分层、换手近似。 |
| `industry` | 行业中性化和分行业稳健性。 |

离线元信息里优先搜索的表名关键词: `Quote`, `Price`, `Daily`, `Trading`, `行情`, `交易`, `日行情`, `复权`, `Adj`。

### 2. 财务/估值/公告日数据 -> `fundamentals`

用途:计算价值、质量、盈利、现金流、成长类可解释因子。

必须找的字段:

| target column | why it matters | common source hint |
|---|---|---|
| `code` | 股票代码。 | secu code / company code |
| `report_period` | 财报报告期截止日。 | end date / report period |
| `ann_date` | 信息真正可见的日期,防 look-ahead 的核心。 | announcement date / publish date |
| `total_assets` | 资产规模、ROA 分母。 | balance sheet |
| `total_equity` | ROE、账面价值。 | shareholder equity |
| `net_income` | 盈利质量、EP、ROE。 | income statement |
| `revenue` | 成长和利润率。 | operating revenue |
| `operating_cash_flow` | 现金流质量。 | cash flow statement |
| `shares_outstanding` | 每股化指标、市值相关计算。 | share capital / total shares |
| `book_value_per_share` | BP 价值因子。 | book value per share |
| `eps` | EP 价值因子和盈利信号。 | earnings per share |

最重要的正确性要求:`ann_date` 必须是真实公告/披露日。不能用 `report_period` 或季度末当成公告日,否则回测会偷看未来。

离线元信息里优先搜索的表名关键词: `Balance`, `Income`, `CashFlow`, `Financial`, `Indicator`, `Forecast`, `公告`, `财务`, `资产负债`, `利润`, `现金流`, `指标`, `估值`。

### 3. 历史股票池/上市状态/行业 -> `universe`

用途:避免幸存者偏差,确定每天横截面中哪些股票可交易/应纳入研究。

必须找的字段:

| target column | why it matters | common source hint |
|---|---|---|
| `date` | 股票池在历史上的生效日期。 | trade date / effective date |
| `code` | 股票代码。 | secu code / constituent code |
| `weight` | 指数成分权重或股票池权重,没有可为空。 | weight |

强烈建议同时找:

| field | why it matters |
|---|---|
| listing date / delisting date | 过滤未上市或已退市样本。 |
| ST status / suspension status | 做可交易性过滤。 |
| industry effective date | 行业分类要按历史生效,不能只用当前行业。 |

离线元信息里优先搜索的表名关键词: `Index`, `Constituent`, `Component`, `Universe`, `StockList`, `Listed`, `Industry`, `ST`, `Suspend`, `指数`, `成分`, `行业`, `上市`, `停牌`。

## 先记录哪些元信息

最少记录:

| file | content |
|---|---|
| `data/metadata/mssql/latest/databases.csv` | 可访问数据库清单。 |
| `data/metadata/mssql/latest/tables.csv` | 当前数据库的 schema/table/type。 |
| `data/metadata/mssql/latest/columns.csv` | 所有表的字段名、类型、精度、是否可空。 |
| `data/metadata/mssql/latest/manifest.json` | 快照时间、当前数据库、表数量、字段数量。 |

可选记录:

| file | content |
|---|---|
| `data/metadata/mssql/latest/row_counts.csv` | 表的近似行数,用于判断主表规模。 |

## 内网连上时立刻执行

```bash
python scripts/mssql_tool.py --env-file config/mssql.env snapshot \
  --output-dir data/metadata/mssql/latest
```

如果权限允许且数据库不太慢,再补近似行数:

```bash
python scripts/mssql_tool.py --env-file config/mssql.env snapshot \
  --output-dir data/metadata/mssql/latest \
  --row-counts
```

如果表特别多,先限定 schema:

```bash
python scripts/mssql_tool.py --env-file config/mssql.env snapshot \
  --schema dbo \
  --output-dir data/metadata/mssql/latest
```

有了这些 CSV,后续离线也可以继续写导出 SQL、字段映射和清洗代码。
