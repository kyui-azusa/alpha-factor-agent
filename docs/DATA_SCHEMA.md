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

## 字段可得性元数据

`panel.attrs["field_availability"]` 是面板构建时附带的内存审计契约,用于说明每个可用于因子表达式的字段在 T 日为何可见。该元数据不替代原始数据校验,但校验层和回测层会据此 fail closed:表达式引用 PIT 敏感字段而缺少可得性证明时,应拒绝执行。

每个字段的元数据至少包含:

| key | dtype | meaning |
|---|---:|---|
| `field` | `string` | 字段名。 |
| `source` | `string` | 字段来源,如 `prices`、`fundamentals`、`derived`、`universe`。 |
| `available_date` | `string` | 信息可得性的日期锚点,如 `date`、`ann_date`、`effective_date`。 |
| `rule` | `string` | 可得性规则的简短说明。 |
| `pit_protected` | `bool` | 是否已经满足点时间约束。 |
| `inputs` | `list[string]` | 可选。推导字段依赖的输入字段。 |

来源规则如下:

| source | rule |
|---|---|
| `prices` | 当日市场字段只能使用同一交易日数据,`available_date = date`。`open/high/low/close/vol/amount` 可按同日行情视为安全;`adj_factor`、`mktcap`、`industry` 等字段必须显式记录来源或推导规则。 |
| `fundamentals` | 财务字段只能由 `pit_merge` 写入,`available_date = ann_date`,且每个 `(date, code)` 单元只能选择最新的 `ann_date <= date` 记录。 |
| `derived` | 推导字段在所有输入字段都 PIT 安全时才安全。例如当前缺失原始市值时,`mktcap = close * shares_outstanding`,其中 `shares_outstanding` 必须来自 PIT 合并后的财务记录。 |
| `universe` | 股票池字段来自历史股票池或成分权重,使用同一交易日或有效日,不能用当前成分股回填历史。 |

需要特别区分代码可证明的边界与外部假设:本项目能测试 `pit_merge` 不会把 `ann_date > date` 的记录并入 T 日面板,并能拒绝绕过元数据的因子/回测路径;但原始库中 `ann_date` 是否真实、财务内容是否混入事后修订、供应商复权字段是否按研究口径正确构造,仍属于数据供应商和抽取流程假设。若从持久化文件重新加载后丢失 `attrs`,应重新构建或补齐元数据,而不是默认放行 PIT 敏感字段。

## 研究运行状态

`RunStore` 使用 SQLite 持久化研究任务。`runs` 保存 `run_id`、`request_id`、父运行、输入指纹、当前状态/阶段、累计产物、稳定错误码、重试次数和完整性标记;`stage_attempts` 保存每个阶段的输入/输出产物与起止时间;`candidates` 保存单候选状态;`retry_requests` 保存幂等重试键。

正常状态按 `draft -> preflight_running -> awaiting_confirmation -> queued -> generating -> validating -> backtesting -> summarizing` 推进,回测阶段可进入下一轮生成或汇总。终态为 `completed`、`partial_completed`、`failed` 或 `canceled`。`partial_completed` 是可查询终态,但 `incomplete` 必须保持为真。基础数据或 PIT 错误应阻断整个运行;单候选失败可以与其他成功候选共同形成部分完成。

相同输入的失败重试复用原 `run_id`,只增加失败阶段的 attempt;相同幂等键不会重复创建工作。输入指纹变化时必须创建带 `parent_run_id` 的子运行,从 `draft` 重新开始,不得覆盖原运行或复用旧产物。

## LLM 生成记录

每个 LLM 内容寻址缓存由同名 `<cache_key>.txt` 响应和 `<cache_key>.json` 生成记录组成。JSON 至少包含 `generation_record_id`、`prompt_hash`、`output_hash`、backend、model、`max_tokens`、temperature、UTC 创建时间和本次是否命中缓存。写入使用同目录临时文件后原子替换。

`generation_record_id` 由 system、prompt 和完整生成参数的缓存键派生,用于复盘同一生成输入,不代表外部模型天然确定。候选 metadata 记录该生成 ID,并由生成 ID、候选顺序、名称和表达式派生稳定 `candidate_id`,从而能回溯具体生成记录。
