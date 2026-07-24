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

### 财务字段质量审计

在将真实财务字段标记为可用于研究之前,调用 `audit_fundamental_quality` 对研究样本中的每个 `(date, code, field)` 做确定性审计。调用方必须为每个字段提供 `FieldQualityPolicy`,至少定义最大信息年龄 `max_age_days`;覆盖率阈值、允许的陈旧比例和陈旧值处置也按字段配置,不能用一个全局阈值掩盖字段差异。

逐记录状态严格互斥:

| status | meaning |
|---|---|
| `valid` | 信号时点已有非空值,且信息年龄未超过字段阈值。 |
| `stale` | 信号时点已有值,但信息年龄超过字段阈值。 |
| `never_available` | 该股票在数据源中从未出现该字段的非空值。 |
| `not_yet_announced` | 非空值存在,但到当前信号时点尚不可用。 |
| `business_excluded` | 按显式业务规则排除;必须同时给出具体 `business_exclusion_reason`。 |

覆盖率分母 `eligible_count` 不含 `business_excluded`,但后者仍单独计数并保留原因。`coverage_ratio = (valid + stale) / eligible_count`,`usable_coverage_ratio = valid / eligible_count`;因此把陈旧值配置为 `exclude` 仍会降低可用覆盖率,不会让缺证据样本通过。`missing_ratio` 只统计 `never_available` 与 `not_yet_announced`,`stale_ratio` 单独报告。

审计输出逐记录明细,以及按字段、日期和行业的覆盖率、新鲜度、最近可用时点、最近公告日/报告期和 lag 统计。`save_fundamental_quality_audit` 将结果保存为 `records.csv`、`fields.csv`、`dates.csv`、`industries.csv` 和 `audit.json`;稳定 `audit_id` 由规则版本、字段策略、明细与汇总共同计算。`preflight_evidence()` 可直接填入 `CapabilityEvidence`,低于可用覆盖率阈值时阻断 PF-013,超过陈旧比例时阻断 PF-014。缺少审计证据不能默认通过。

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

面板还可附带四个确定性市场状态字段:`market_return_20d_lagged`、
`market_volatility_20d_lagged`、`regime_bull`、`regime_high_vol`。它们只使用截至 T-1 的
全市场等权收益计算;T 日价格变化不得改变 T 日状态。表达式只能通过
`where(regime_*, on_true, on_false)` 使用已登记的二元状态,不能在表达式内写比较或 Python
条件语句。

## `performance_forecasts`

业绩预告事件表。一行表示一只股票针对一个报告期发布的一次有效预告。原始数据来自
`JYDB.dbo.LC_PerformanceForecast`,去重、报告期选择和列名映射需由后续专门导出模块实现。

| column | dtype | nullable | meaning |
|---|---:|---:|---|
| `code` | `string` | no | A 股股票代码。 |
| `forecast_id` | `string` | no | 稳定公告/记录标识,用于去重和缓存键。 |
| `forecast_publish_date` | `datetime64[ns]` | no | 原始 `InfoPublDate`;T 日公告从 T+1 交易日起可用。 |
| `forecast_end_date` | `datetime64[ns]` | no | 预告对应报告期。 |
| `forecast_type` | `string` | yes | 原始 `ForcastType` 的版本化映射。 |
| `forecast_reason` | `string` | yes | 原始 `ForcastReason`;不能与正文语义特征重复计入对照组。 |
| `forecast_growth_floor` | `float64` | yes | 原始 `EGrowthRateFloor`;扭亏/首亏等负基数情形保持缺失。 |
| `forecast_growth_ceiling` | `float64` | yes | 原始 `EGrowthRateCeiling`;扭亏/首亏等负基数情形保持缺失。 |
| `forecast_profit_floor` | `float64` | yes | 原始 `EProfitFloor`,单位必须由导出清单固定。 |
| `forecast_profit_ceiling` | `float64` | yes | 原始 `EProfitCeiling`,单位必须由导出清单固定。 |
| `forecast_last_profit` | `float64` | yes | 原始 `LastProfit`,不得用事后修订值回填。 |
| `forecast_consensus_np_yoy` | `float64` | yes | 原始 `NPYOYConsistentForecast`;必须确认是事件时点快照。 |
| `forecast_content` | `string` | yes | 原始 `ForcastContent`,只用于离线语义抽取,不直接进入回测。 |
| `forecast_text_feature` | `float64` | yes | 按公告哈希、模型和 prompt 版本冻结的离线语义特征。 |

事件可得性边界为**下一交易日**:所有结构化字段与离线文本特征都必须在
`next_trading_date(forecast_publish_date) <= date` 时才可合并。回测只读冻结后的数值缓存,
在断网且没有 API key 时必须可逐字节复现。

## A 股知识库契约

`knowledge/a_share/v1.json` 是生成阶段的版本化事实源,包含来源、字段、因子先验和制度规则。
每个来源记录访问日期、覆盖范围、许可/使用边界;每个字段记录来源表、频率、可得时间、PIT
规则、可回测状态和风险。运行时 `field_catalog` 只暴露“面板实际存在”与“正式知识库已登记为
可回测”的交集。候选若声明 `backtestable_status = currently_backtestable`,必须通过
`knowledge_citations` 引用所有字段来源;未登记字段不得因 LLM 的声明而升级为可回测。

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

## 研究运行状态

`RunStore` 使用 SQLite 持久化研究任务。`runs` 保存 `run_id`、`request_id`、父运行、输入指纹、当前状态/阶段、累计产物、稳定错误码、重试次数和完整性标记;`stage_attempts` 保存每个阶段的输入/输出产物与起止时间;`candidates` 保存单候选状态;`retry_requests` 保存幂等重试键。

正常状态按 `draft -> preflight_running -> awaiting_confirmation -> queued -> generating -> validating -> backtesting -> summarizing` 推进,回测阶段可进入下一轮生成或汇总。终态为 `completed`、`partial_completed`、`failed` 或 `canceled`。`partial_completed` 是可查询终态,但 `incomplete` 必须保持为真。基础数据或 PIT 错误应阻断整个运行;单候选失败可以与其他成功候选共同形成部分完成。

相同输入的失败重试复用原 `run_id`,只增加失败阶段的 attempt;相同幂等键不会重复创建工作。输入指纹变化时必须创建带 `parent_run_id` 的子运行,从 `draft` 重新开始,不得覆盖原运行或复用旧产物。

## LLM 生成记录

每个 LLM 内容寻址缓存由同名 `<cache_key>.txt` 响应和 `<cache_key>.json` 生成记录组成。JSON 至少包含 `generation_record_id`、`prompt_hash`、`output_hash`、backend、model、`max_tokens`、temperature、UTC 创建时间和本次是否命中缓存。写入使用同目录临时文件后原子替换。

`generation_record_id` 由 system、prompt 和完整生成参数的缓存键派生,用于复盘同一生成输入,不代表外部模型天然确定。候选 metadata 记录该生成 ID,并由生成 ID、候选顺序、名称和表达式派生稳定 `candidate_id`,从而能回溯具体生成记录。
