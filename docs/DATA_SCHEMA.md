# DATA_SCHEMA — 输入数据契约

本项目的数值结论只来自确定性代码。真实聚源数据接入前,可使用 `src.utils.synthetic` 生成同结构样例数据做工程验证。日期和时点字段统一使用无时区的 `datetime64[ns]`,并解释为 `Asia/Shanghai` 本地时间;股票代码字段统一使用字符串。

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
| `ann_date` | `datetime64[ns]` | no | 公告自然日,不得用 `report_period` 替代。 |
| `ann_time` | `datetime64[ns]` | yes | 经数据源认证的精确发布时间。午夜占位、推断值或仅有日期时必须为空;防守性实现仍会把 `00:00:00` 自动降级为日期级记录。 |
| `total_assets` | `float64` | yes | 总资产。 |
| `total_equity` | `float64` | yes | 归母或股东权益。 |
| `net_income` | `float64` | yes | 净利润。 |
| `revenue` | `float64` | yes | 营业收入。 |
| `operating_cash_flow` | `float64` | yes | 经营现金流。 |
| `shares_outstanding` | `float64` | yes | 总股本。 |
| `book_value_per_share` | `float64` | yes | 每股净资产。 |
| `eps` | `float64` | yes | 每股收益。 |

关键约束是比较信息可用时点与信号计算时点,而不是只比较自然日。调用 `pit_merge` 时必须显式提供 `signal_time` 和 `availability_time_col`:

- 数据源已经认证精确发布时间时,配置 `fundamental_availability_time_col = "ann_time"`,使用 `ann_time <= signal_time` 判断同日可用性。盘前公告可进入之后生成的当日信号;盘中公告只能进入更晚的信号;盘后公告不能进入当日收盘信号。任何 `00:00:00` 值都按日期级占位处理,不会作为盘前精确时刻放行。
- 只有 `ann_date` 或精确时刻缺失时,该记录从严格的下一交易日起可用。即使上游把日期写成午夜,也不能将其解释为盘前精确发布时间。
- 默认 `fundamental_availability_time_col = None`,所有记录走保守规则。仅出现一个 `ann_time` 列不会自动启用精确时点,必须由数据接入配置显式认证。
- `ann_time` 非空但自然日与 `ann_date` 不一致、时点带未知时区或信号时点不在对应交易日时,合并直接失败。

## `universe`

历史股票池表。一行表示某只股票在某日属于研究股票池,用于防幸存者偏差。

| column | dtype | nullable | meaning |
|---|---:|---:|---|
| `date` | `datetime64[ns]` | no | 交易日。 |
| `code` | `string` | no | 股票代码。 |
| `weight` | `float64` | yes | 股票池权重或成分权重;没有权重时可为空。 |

主键:`date, code`。加载后应以该表过滤 `prices` 和面板数据,不能用当前成分股回填历史。

## 面板约定

处理后的 `panel` 使用 `MultiIndex[date, code]`,其中 `date` 为交易日、`code` 为股票代码。行情字段来自当日市场数据;财务字段来自 `pit_merge`,保证每行只包含在该行信号时点已经可用的数据。内部合并使用的 `information_available_at` 和 `publication_time_status` 不进入最终因子列,避免被误选为候选字段。未来收益由 `get_forward_returns` 单独生成,列名为 `fwd_ret_1`, `fwd_ret_5`, `fwd_ret_20`,不得作为因子表达式可用字段。

`panel.attrs["pit_availability_audit"]` 是本次合并的聚合审计,至少包含规则版本、信号时点、认证的精确发布时间列、各发布时间状态数量、保守延后记录数、因样本交易日历结束而尚未解析的记录数,以及实际匹配到面板行的状态数量。`publication_time_status` 的稳定值为 `date_only`、`exact_pre_market`、`exact_trading_session`、`exact_after_market`、`exact_non_trading_day`。

## 字段可得性元数据

`panel.attrs["field_availability"]` 是面板构建时附带的内存审计契约,用于说明每个可用于因子表达式的字段在 T 日为何可见。该元数据不替代原始数据校验,但校验层和回测层会据此 fail closed:表达式引用 PIT 敏感字段而缺少可得性证明时,应拒绝执行。

每个字段的元数据至少包含:

| key | dtype | meaning |
|---|---:|---|
| `field` | `string` | 字段名。 |
| `source` | `string` | 字段来源,如 `prices`、`fundamentals`、`derived`、`universe`。 |
| `available_date` | `string` | 信息可得性的日期或时点锚点,如 `date`、`information_available_at`、`effective_date`。 |
| `rule` | `string` | 可得性规则的简短说明。 |
| `pit_protected` | `bool` | 是否已经满足点时间约束。 |
| `inputs` | `list[string]` | 可选。推导字段依赖的输入字段。 |

来源规则如下:

| source | rule |
|---|---|
| `prices` | 当日市场字段只能使用同一交易日数据,`available_date = date`。`open/high/low/close/vol/amount` 可按同日行情视为安全;`adj_factor`、`mktcap`、`industry` 等字段必须显式记录来源或推导规则。 |
| `fundamentals` | 财务字段只能由 `pit_merge` 写入,`available_date = information_available_at`,且每个 `(date, code)` 单元只能选择最新的 `information_available_at <= signal_time` 记录。 |
| `derived` | 推导字段在所有输入字段都 PIT 安全时才安全。例如当前缺失原始市值时,`mktcap = close * shares_outstanding`,其中 `shares_outstanding` 必须来自 PIT 合并后的财务记录。 |
| `universe` | 股票池字段来自历史股票池或成分权重,使用同一交易日或有效日,不能用当前成分股回填历史。 |

需要特别区分代码可证明的边界与外部假设:本项目能测试 `pit_merge` 不会把发布时间晚于信号时点的记录并入面板,能对缺失时刻执行下一交易日保守规则,并能拒绝绕过元数据的因子/回测路径;但原始库中 `ann_date`/`ann_time` 是否真实、财务内容是否混入事后修订、供应商复权字段是否按研究口径正确构造,仍属于数据供应商和抽取流程假设。若从持久化文件重新加载后丢失 `attrs`,应重新构建或补齐元数据,而不是默认放行 PIT 敏感字段。
