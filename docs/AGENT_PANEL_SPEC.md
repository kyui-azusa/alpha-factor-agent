# AGENT PANEL SPEC — 给 Codex 的实现说明

研究面板(`panel/`):一个**独立的** Vue 应用,用来在答辩现场演示"事件 → 市场反应"的关联,
并让人自己选股票/组合看效果。

> **不要动 `platform/`。** 现有站点(想法流 + 工单入口,`alpha.cihua.run`)项目所有者已确认满意,
> 本任务不修改它的任何文件、不改 `build.py`、不改 `intake_service.py`、不改 `static/style.css`。
> 两者是并列的两个面,共用视觉语言但不共用代码。

---

## 0. 通用约定

- Node `^20.19.0 || >=22.12.0`,pnpm。Vue 3 + Vite + TypeScript + vue-router + pinia。
- 界面骨架从 `/Users/azusa/dev/service/chatzzy/ChatZZY` 复制。**注意:那是一个未改动过的
  `create-vue` 脚手架**,只有默认的 `HelloWorld.vue` / `TheWelcome.vue` / `counter.ts`,
  没有任何聊天代码。它提供的是工具链配置(vite/eslint/prettier/tsconfig),不是可复用的组件。
  复制后**删掉** `src/components/*`、`src/views/*`、`src/stores/counter.ts` 的示例内容。
- 所有数值在**构建期**由 Python 算好导成 JSON;前端只做读取、筛选、加减乘除和绘图。
- 每个阶段结束跑 `pnpm type-check && pnpm lint`。

---

## 1. 架构决策:静态优先,构建期算完

```
Python(构建期,确定性)                浏览器(运行期)
  聚源 JYDB
    → src/backtest 既有回测        →   读 JSON
    → scripts/export_panel_data.py →   组合加权(纯算术)
    → panel/public/data/*.json     →   绘图
                                       ↑ 零后端 · 零内置密钥 · 断网可跑
```

唯一的例外是 AgentConsole 的自由输入(§5 P2.5):**由用户自己配置 baseUrl + key**,
浏览器直接请求,项目不内置任何密钥、不代付任何 token。且该路径**只把自然语言翻译成视图参数,
不产生任何数值** —— 铁律 1 不受影响。预设 chip 与全部图表在未配置时照常可用。

三条既有约束同时指向这个方案,**不要改成"前端调后端算"**:

| 约束 | 出处 | 后果 |
|---|---|---|
| 回测里绝不调用 LLM | 铁律 1(CLAUDE.md) | 运行期不能有任何模型调用 |
| 不新增后端端点 | ADR-0020 后果条款 | 不加 API server,不动 `intake_service.py` |
| 公开端点会被刷 | 本项目实际风险 | 无端点 = 无 token 消耗 = 无滥用面 |

**答辩现场必须能断网演示。** 这是硬指标:`pnpm build` 出来的 `dist/` 双击 `index.html`
(或 `pnpm preview`)即可完整运行,不依赖任何网络请求。

---

## 2. 红线(必须遵守,来自 ADR-0003 / 0007 / 0020)

panel **可以**展示:

- 日行情 OHLCV、涨跌幅、K 线 —— 公开市场数据;
- 业绩预告的**披露日期**与**已公开的结构化字段**(预增/预减类型、幅度区间);
- 方法与流程(受限算子白名单的**名字**、PIT 规则、样本外划分);
- 基线因子的**类别名**(价值/质量/动量/波动率/流动性)与其回测图表。

panel **不得**展示:

- **真实数据上跑出来的最终因子表达式**;
- **调优后的参数**(窗口长度、分位阈值、权重等具体取值);
- 聚源字段清单 / 库表结构(ADR-0007 明令禁止,`data/metadata/` 已在 `.gitignore`);
- 任何来自 `config/mssql.env` 的连接信息。

导出脚本里要有一道显式的白名单过滤,不是靠人记得。见 §4 的 `REDACT` 约定。

---

## 3. 目录结构

```
panel/                          # 新建,与 platform/ 并列
├── package.json
├── vite.config.ts
├── index.html
├── public/
│   └── data/                   # 构建期产物,gitignore 掉大文件
│       ├── manifest.json       # 有哪些股票、日期范围、生成时间
│       ├── stocks/<code>.json  # 单只股票的 OHLCV + 事件标记(懒加载)
│       ├── events.json         # 业绩预告事件总表(轻量,全量加载)
│       └── factors/<id>.json   # 因子回测结果(IC 序列、分组收益、净值)
└── src/
    ├── main.ts
    ├── router/index.ts
    ├── stores/
    │   ├── market.ts           # 行情数据加载与缓存
    │   └── portfolio.ts        # 用户选的股票与权重
    ├── components/
    │   ├── KLineChart.vue      # K 线 + 事件标记
    │   ├── StockPicker.vue     # 股票搜索与多选
    │   ├── PortfolioBuilder.vue# 权重编辑 + 净值曲线
    │   ├── ReturnStats.vue     # 涨跌幅 / 区间收益 / 回撤统计
    │   └── AgentConsole.vue    # 预设问题 chip + 结果展示
    └── views/
        ├── ExplorerView.vue    # 主页:选股 → K线 → 事件
        ├── PortfolioView.vue   # 组合构建与对比
        └── FactorView.vue      # 因子回测结果浏览
```

`panel/public/data/` 里除 `manifest.json` 外全部 **gitignore**(单只股票 7 年 OHLCV 约
100–150 KB,几百只就是几十 MB,不进仓库)。构建前跑一次导出脚本即可重建。

---

## 4. 数据导出(Python 侧)

**新建** `scripts/export_panel_data.py`。不要改 `src/` 下的既有模块。

```python
def export_manifest(out_dir: Path) -> None: ...
def export_stocks(codes: list[str], out_dir: Path) -> None: ...
def export_events(out_dir: Path) -> None: ...
def export_factor_result(factor_id: str, out_dir: Path) -> None: ...
```

### `manifest.json`

```json
{
  "generated_at": "2026-07-23T10:00:00+08:00",
  "date_range": ["2015-01-01", "2021-12-31"],
  "stocks": [{"code": "000001.SZ", "name": "平安银行", "industry": "银行"}],
  "factors": [{"id": "baseline_momentum_20d", "label": "动量(20日)", "category": "动量"}]
}
```

### `stocks/<code>.json`

**复权后**的 OHLCV。注意:`data/raw/prices_raw.pkl` 里**没有** `adj_factor` 列,
复权因子在 `data/raw/adj_factors.csv`,是**事件记录**(每次除权除息一行),
需用 `pd.merge_asof(direction="backward")` 按 `ex_date` 展开到每个交易日后再乘。
**不要直接用未复权价算收益率** —— 那是本项目刚修掉的一个真 bug(见 `sql/export_prices.sql` 注释)。

```json
{
  "code": "000001.SZ",
  "name": "平安银行",
  "industry": "银行",
  "dates":  ["2015-01-05", "..."],
  "ohlc":   [[16.65, 16.95, 16.40, 16.80], ["..."]],
  "volume": [123456789, "..."],
  "ret":    [0.0123, "..."]
}
```

数组并列、按 `dates` 对齐,不要用 `[{date, open, high...}]` 的对象数组 —— 体积差三倍。

### `events.json`

```json
{
  "events": [{
    "code": "000001.SZ",
    "publ_date": "2021-01-21",
    "usable_from": "2021-01-22",
    "type": "预增",
    "growth_floor": 50.0,
    "growth_ceiling": 70.0
  }]
}
```

`usable_from` **必须**是 `publ_date` 的下一个交易日 —— PIT 保守规则(披露时间粒度不一致,
部分记录只有日期没有时刻,不能假设盘中可用)。前端在 K 线上标记时用 `publ_date` 画点,
但任何"如果当时买入"的计算一律从 `usable_from` 起算。**这两个日期不能混用**,
混用就是 look-ahead,是本项目最核心的红线。

### `REDACT` 约定

导出脚本顶部定义:

```python
# 允许出现在 panel 数据里的因子元数据字段。白名单之外的一律不导出。
FACTOR_PUBLIC_FIELDS = {"id", "label", "category", "ic_series", "quantile_returns",
                        "long_short_nav", "turnover"}
# 明令禁止:真实数据上的表达式与调优参数(ADR-0020)
FACTOR_REDACTED_FIELDS = {"expression", "params", "window", "threshold", "weights"}
```

导出时按白名单挑字段,并对 `FACTOR_REDACTED_FIELDS` 做一次断言,命中就抛异常。
**靠代码拦,不靠人记得。**

---

## 5. 页面与交互

### P0 — ExplorerView(主页,必须完成)

1. 顶部搜索框选股票(代码或名称),支持多选;
2. **K 线图**,可切换区间(近 1 月 / 3 月 / 1 年 / 全部);
3. K 线上**用标记标出业绩预告披露日**,鼠标悬停显示预告类型与幅度区间;
4. 右侧统计卡:区间涨跌幅、年化波动率、最大回撤。

**第 3 条是这个 panel 的核心价值**,不是装饰。它把研究主题("事件之后市场怎么走")
变成一眼能看见的东西 —— 选一只有预增公告的股票,标记点后面那段走势就是全部论证的直观版。
其他都可以砍,这条不能砍。

### P1 — PortfolioView(组合)

1. 从已选股票构建组合,支持**等权**与**自定义权重**(权重和自动归一化并显示);
2. 组合净值曲线,叠加一条基准(等权全市场或指数,取构建期算好的);
3. 组合层面的涨跌幅 / 波动率 / 最大回撤 / 夏普;
4. **组合收益在前端算**:`portfolio_ret[t] = Σ w_i × ret_i[t]`,纯算术,不需要后端。

权重变更要即时重算重绘(几百个交易日的加权求和,前端毫秒级)。

### P2 — FactorView(因子结果浏览)

读 `factors/<id>.json` 渲染 IC 序列、分组收益柱状图、多空净值曲线。
**只展示图和类别名,不展示表达式与参数**(§2 红线)。

### P2.5 — AgentConsole(用户自带 key)

仿 α-Mind 的输入框 + "猜你想问" chip。分两层,**第一层不依赖任何配置**:

1. **预设 chip 走预计算结果,不调 LLM。** 每个 chip 对应一个已导出的 `factors/<id>.json`
   或一组股票,点了就是切换视图 + 展示结论文本。断网可用,答辩演示走这条。
2. **自由输入需用户自己配置 LLM。** 见下。

#### 配置结构

沿用 ADR-0013 与 `src/llm/client.py` 的口径(OpenAI-compatible),前端存 `localStorage`:

```ts
interface LLMSettings {
  baseUrl: string   // 如 https://api.openai.com/v1 或自建代理 / vLLM / Ollama
  apiKey: string
  model: string     // 如 gpt-4.1-mini
}
// localStorage key: "alpha-panel-llm"
```

设置入口是一个齿轮按钮 + 弹窗,三个输入框。**未配置时自由输入框禁用并提示"需先配置模型",
预设 chip 仍然可用。**

#### 密钥处理规矩

- key **只存在于用户浏览器的 localStorage**,只发往用户自己填的 `baseUrl`,不发往任何其他地址;
- **绝不写进任何日志、错误上报、URL query、构建产物**;报错信息里要做掩码(只留后 4 位);
- 设置弹窗里明写一行:密钥以明文存于本机浏览器,公用电脑请用完清除;
- 提供"清除配置"按钮。

#### ⚠️ CORS 是这个功能最大的技术风险

panel 没有后端(§1),浏览器**直接**请求用户填的 `baseUrl`。如果那个地址不返回 CORS 头,
请求会被浏览器拦掉,而且**没有服务端可以代理**。已知情况:

| 后端 | CORS |
|---|---|
| OpenAI 官方 API | 可用(需在请求里显式允许浏览器环境) |
| 自建 one-api / new-api 类网关 | 通常可配,默认多为允许 |
| vLLM | 需启动时配 `--allowed-origins` |
| Ollama | 需设环境变量 `OLLAMA_ORIGINS` |

**实现要求**:捕获 CORS 失败并给出**可操作**的报错——不要只显示 "Network Error",
要提示"目标地址未允许浏览器跨域访问,请检查服务端 CORS 配置"并附上上表。
这个错误如果提示不清,用户会以为是 key 填错了,排查方向全错。

#### 铁律 1 在这里怎么落

LLM **只做"自然语言 → 已有视图的参数"**,输出必须是结构化 JSON:

```json
{"action": "show_stocks", "codes": ["000001.SZ"], "range": "2021-01-01/2021-06-30"}
{"action": "show_factor", "id": "baseline_momentum_20d"}
{"action": "build_portfolio", "codes": ["..."], "weights": "equal"}
```

**绝不允许它产生任何数值。** 所有涨跌幅、IC、净值一律来自预计算 JSON。
解析失败就提示重说,不要让模型的自由文本直接进结果区。

---

## 6. 图表库选型

**用 `klinecharts`**(`pnpm add klinecharts`)。理由:

- 专为 K 线做的,开箱即有蜡烛图 / 成交量 / 十字光标 / 区间缩放,不用自己拼;
- **原生支持覆盖物(overlay)标注**,正好用来标业绩预告披露点 —— 这是 P0 第 3 条的关键;
- 体积远小于 ECharts 全量包,中文文档完整。

净值曲线、分组收益柱状图这类普通图**不要**再引第二个大库,用 SVG 手写或极轻量的实现即可。
组合净值就是一条折线,不值得为它装 ECharts。

---

## 7. 分阶段验收

| 阶段 | 完成标志 |
|---|---|
| **A. 骨架** | 从 ChatZZY 复制脚手架、清掉示例内容、路由三个页面可切换、`pnpm type-check` 通过 |
| **B. 数据** | `scripts/export_panel_data.py` 能导出 manifest + 至少 50 只股票 + events,JSON 结构符合 §4,`usable_from` 断言存在 |
| **C. P0** | ExplorerView 能选股、画 K 线、标出预告点、显示区间涨跌幅 |
| **D. P1** | PortfolioView 能建组合、改权重、画净值、出统计 |
| **E. 断网验收** | `pnpm build` 后,**断开网络**,`pnpm preview` 下 P0/P1/P2 与预设 chip 全部可用 |
| **F. Agent** | 未配置时预设 chip 可用、自由输入禁用且有提示;配置后能把自然语言翻成视图参数;CORS 失败有可操作报错 |

**E 是硬指标**,答辩现场不能赌网络。注意 E 的口径:断网时**预设 chip 必须可用**,
自由输入不可用是预期行为(它本来就要连用户自己的模型服务)。

---

## 8. 时间与取舍

距答辩约 1.5–2 天,且主线(七年窗口重跑 + 增量检验)尚未完成。

**如果时间不够,按 A → B → C → E 交付,砍掉 P1 / P2 / P2.5。**
一个能选股、画 K 线、标出预告事件、断网可跑的 ExplorerView,已经完整表达了研究主题;
而一个功能齐全但现场跑不起来的 panel,价值是零。

AgentConsole 若要做,**先做第一层(预设 chip,不依赖配置)**,自由输入那半留到最后。
第一层几乎没有实现成本(就是切视图 + 显示文本),却是答辩现场真正会用到的那部分;
自由输入依赖用户当场配好 baseUrl 和 key,还要赌对方服务端的 CORS —— 不适合当现场演示路径。

不要为了铺功能牺牲 E。
