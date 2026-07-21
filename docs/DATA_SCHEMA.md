# DATA_SCHEMA — 输入数据契约

本项目的数值结论只来自确定性代码。真实聚源数据接入前,可使用 `src.utils.synthetic` 生成同结构样例数据做工程验证。所有日期字段统一使用 `datetime64[ns]`,股票代码字段统一使用字符串。

## `prices`

日频复权行情表。一行表示某只股票在一个交易日的行情。

| column | dtype | nullable | meaning |
|---|---:|---:|---|
| `date` | `datetime64[ns]` | no | 交易日。 |
| `code` | `string` | no | 股票代码。 |
| `open` | `float64` | no | 前复权开盘价。 |
| `high` | `float64` | no | 前复权最高价。 |
| `low` | `float64` | no | 前复权最低价。 |
| `close` | `float64` | no | 前复权收盘价,收益计算基准。 |
| `vol` | `float64` | no | 成交量。 |
| `amount` | `float64` | no | 成交额。 |
| `adj_factor` | `float64` | no | 复权因子。 |
| `mktcap` | `float64` | yes | 总市值或流通市值,用于中性化与换手率近似。 |
| `industry` | `string` | yes | 行业分类。 |

主键:`date, code`。要求同一股票价格按日期升序排列。

## `fundamentals`

财务和估值字段表。一行表示某只股票某个报告期在某个公告日之后可见的一组财务数据。

| column | dtype | nullable | meaning |
|---|---:|---:|---|
| `code` | `string` | no | 股票代码。 |
| `report_period` | `datetime64[ns]` | no | 财报报告期截止日,如季度末或年末。 |
| `ann_date` | `datetime64[ns]` | no | 公告日。点时间合并只允许在 `ann_date <= date` 时使用该行。 |
| `total_assets` | `float64` | yes | 总资产。 |
| `total_equity` | `float64` | yes | 归母或股东权益。 |
| `net_income` | `float64` | yes | 净利润。 |
| `revenue` | `float64` | yes | 营业收入。 |
| `operating_cash_flow` | `float64` | yes | 经营现金流。 |
| `shares_outstanding` | `float64` | yes | 总股本。 |
| `book_value_per_share` | `float64` | yes | 每股净资产。 |
| `eps` | `float64` | yes | 每股收益。 |

关键约束:`ann_date` 是信息可得性的唯一时间边界。任何 T 日因子都只能使用 `ann_date <= T` 的最新公告记录。`report_period` 不能替代 `ann_date` 做可得性判断。

## `universe`

历史股票池表。一行表示某只股票在某日属于研究股票池,用于防幸存者偏差。

| column | dtype | nullable | meaning |
|---|---:|---:|---|
| `date` | `datetime64[ns]` | no | 交易日。 |
| `code` | `string` | no | 股票代码。 |
| `weight` | `float64` | yes | 股票池权重或成分权重;没有权重时可为空。 |

主键:`date, code`。加载后应以该表过滤 `prices` 和面板数据,不能用当前成分股回填历史。

## 面板约定

处理后的 `panel` 使用 `MultiIndex[date, code]`,其中 `date` 为交易日、`code` 为股票代码。行情字段来自当日市场数据;财务字段来自 `pit_merge`,保证每行只包含当日已经公告的数据。未来收益由 `get_forward_returns` 单独生成,列名为 `fwd_ret_1`, `fwd_ret_5`, `fwd_ret_20`,不得作为因子表达式可用字段。
