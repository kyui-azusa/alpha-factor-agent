# PLATFORM V2 SPEC — 知识图谱 + 成果展示区

> 给 coding agent(Codex)的实现说明。与 `docs/BUILD_SPEC.md` 同级,但只覆盖 `platform/`。
> 配套决策见 **ADR-0019**(方法依赖图)、**ADR-0020**(curation 即壁垒)。

---

## 0. 背景与硬边界(先读,决定了后面每一条)

| 事实 | 影响 |
|---|---|
| 今天 2026-07-21,答辩 07-24/25,**只剩 3–4 天** | 任何超过 1.5 天的平台工程都要砍 |
| **答辩即项目终点**,没有"答辩后再做" | 一切"为长期价值"的基建(版本流、权限体系)失去意义 |
| ADR-0001:研究是主线(Project Spine),**平台是副产品** | 平台不得挤占模型/PPT/论文的时间 |
| 真交付仍缺口很大:模型形态未定、论文是 AI 初稿 | 平台只能拿"边角料时间" |

**站点的三个动机(用户确认的优先级):**

1. **C — 课程期同学分享面(最重)。** 同学现在就在看。壁垒的真实含义是:**别让同学在他们自己答辩前抄走方法**。
2. **A — 答辩现场展示物。** 打开给老师看,证明过程公开、有外部反馈闭环。
3. **B — 个人作品集(最轻)。** 站点长期挂着,半年后陌生人打开要仍然说得通。

**由 C 推出的一条关键规则:**
> **红线安全 ≠ 防抄安全。** ADR-0003/0007 的红线管的是"别漏真 alpha";动机 C 管的是"别让方法被提前复制"。论文全文对红线是安全的(全篇合成数据 + mock 因子),但对防抄是**最直接的送人头**——它就是完整方法论。两套判断必须分开做。

---

## 1. 核心设计原则:curation 即壁垒

**不要建访问控制系统。** 本方案**明确放弃**四层 tier / 解锁 token / 微信软门 / 口令层(评审过程见 §5)。

代之以一句话规则:

> **`build.py` 只渲染写进内容文件的东西。没写进去的,服务器上根本不存在。**

理由:任何 token 体系都比不过"它不在那儿"。对一个 3 天后终结的项目,curation 是**更强且成本为零**的壁垒。

**落到实现上的三条硬约束:**

1. 站点产物(`dist/index.html` + 上传到 `/var/www/` 的任何文件)**只包含内容文件里显式写出的内容**。禁止任何"扫描目录自动收录""从代码自动抽取"的逻辑 —— 自动化会忠实地把你不想公开的东西一起搬上去。
2. **不新增任何后端端点**(§4 的工单徽章除外,它只改现有响应的一个字段)。不引入 GitHub Contents API、不引入 tag/manifest、不引入 token。
3. 每个内容文件带一个 `public: true|false` 开关,**默认 `false`**(fail-closed)。`build.py` 只渲染 `public: true` 的条目。

---

## 2. P1 — 知识图谱(必做,最高优先级)

### 2.1 它是什么,为什么它排第一

论文 §方法 里有一句核心主张:

> 因子的"可解释性"不再停留于自然语言的经济故事,而是可以**一路回溯到具体字段与有限算子**,做到真正可审计。

**知识图谱就是这句话的可视化证据。** 它不是装饰,是论点的现场演示。

它**一鱼三吃**,是本方案里唯一同时喂三个真交付的东西:

- 站点上的交互图 →(展示面)
- 导出静态 SVG → **直接进 PPT**(PowerPoint 原生支持 SVG)
- 同一张图 → **进论文**,论文目前只有文字声称"可回溯",缺图

且它**防抄风险低**:展示的是方法的*形状*(字段→算子→因子→指标),不是可复制的实现。炫耀价值高、被抄价值低 —— 正是该放的东西。

### 2.2 数据源:手写 `platform/content/graph.yaml`

**不要从代码自动抽。** 理由三条:
1. 规模不值得 —— 约 40 节点手写一小时,自动抽要写四套解析器。
2. **边抽不出来** —— "ICIR 依赖 Rank IC" 这种语义依赖,代码里没有可靠信号。
3. **自动抽破坏壁垒** —— 它会忠实地把所有字段名、真因子一起抽出来。手写 = 逐条决定图上出现什么,这本身就是闸门。

### 2.3 Schema

```yaml
# platform/content/graph.yaml
layers:                       # 顺序即渲染顺序(桌面左→右,移动上→下)
  - id: field
    label: 原始字段
  - id: align
    label: 对齐与预处理
  - id: operator
    label: 白名单算子
  - id: factor
    label: 因子类别
  - id: metric
    label: 评价指标

nodes:
  - id: ann_date
    layer: field
    label: 公告日 ann_date
    one_liner: 财报对外披露的日期。因子在 T 日只能用 ann_date ≤ T 的记录 —— 这是防前视的锚点。
    refs: [docs/DATA_SCHEMA.md, src/utils/align.py]
    emphasis: true            # 可选:渲染成高亮节点(核心概念)
    code_symbol: null         # 可选:对应代码符号,防漂移测试用

  - id: safe_div
    layer: operator
    label: safe_div
    one_liner: 防零除的安全除法,是估值/盈利类比率因子的基础算子。
    refs: [src/factors/engine.py]
    code_symbol: safe_div     # 必须存在于 FACTOR_FUNCTIONS

guards:                       # 横切"防线",不占列,渲染成挂在节点上的徽章
  - id: no_lookahead
    label: 防 look-ahead
    one_liner: 因子在 T 日只能使用 ann_date ≤ T 的数据。
    attaches: [ann_date, pit_merge]
  - id: oos_rolling
    label: 样本外按日期滚动
    one_liner: train_end 之后统一为样本外,禁止随机打乱。
    attaches: [rank_ic, ic_ir]

edges:
  - {from: ann_date,  to: pit_merge, kind: computes}
  - {from: rank_ic,   to: ic_ir,     kind: derives}
```

**边的语义(`kind`):**
- `computes` — 计算依赖:目标节点的计算需要源节点。
- `derives` — 指标派生:目标指标由源指标推出(如 ICIR ← Rank IC)。

**方向约定:边一律从上游指向下游**(字段 → 算子 → 因子 → 指标)。"回溯"= 沿边反向遍历。

### 2.4 图内容清单(建议初版,可增删)

| 层 | 建议节点 |
|---|---|
| `field` | close, open, high, low, volume, adj_factor, **ann_date**, report_period, eps, net_income, total_assets, total_equity, operating_cash_flow |
| `align` | **pit_merge**, 复权(adj_factor), 前向收益, winsorize, zscore, neutralize(行业市值中性化) |
| `operator` | rank, cs_rank, ts_mean, ts_std, delay, delta, safe_div, signed_log |
| `factor` | 价值, 质量, 动量, 低波动, 流动性(**只到类别 + 基线因子名,不放具体表达式**) |
| `metric` | Rank IC, ICIR, 分组收益, 多空收益, 换手率, 成本后收益 |
| `guards` | 防 look-ahead, 样本外滚动划分, 禁随机打乱, 交易成本扣减 |

> **粒度红线:`factor` 层只放类别与基线因子名,不放任何具体因子表达式。** 图的结构本身(字段→算子→因子)已完整表达"可回溯",不需要暴露式子。**图证明的是"我的方法可审计",不是"我的因子是什么"。**

### 2.5 渲染:`build.py` 预计算布局 + 内联静态 SVG

**不引任何图库。** d3(~270KB)/cytoscape(~400KB)要整个内联进单文件 HTML,为一张 40 节点的图不值。更关键:**这是分层 DAG,力导向布局会把层次甩成一坨抖动的毛球**,恰好毁掉要展示的东西。

**实现要求:**

- 新建 `platform/graph.py`,导出 `load_graph() -> Graph` 与 `layout(graph) -> LaidOutGraph`。
- 布局算法:**分层 + 重心法排序**
  1. 节点按 `layer` 分列(列 = layer 顺序索引)。
  2. 层内顺序用重心启发式(barycenter)迭代 2 遍减少连线交叉。
  3. **平局一律按 `id` 字典序打破** —— 保证同一份 yaml 每次构建产出**逐字节相同**的 SVG(git diff 才有意义,也便于导出物复现)。
- 输出:`render_svg(laid_out) -> str`,纯 SVG 字符串,内联进 `dist/index.html`。
- 连线用二次贝塞尔,节点用 `<g data-node-id="...">` 便于 JS 选中。
- 配色沿用 `static/style.css` 的深色主题变量,每层一个色相。

### 2.6 交互:图负责震撼,回溯面板负责讲清楚

约 120 行原生 JS(内联,和现有 `JS` 常量一个套路):

- **点击/悬停任一节点** → 计算其**全部上游祖先**(沿边反向做传递闭包)→ 高亮祖先节点与路径边,其余节点/边淡出(`opacity: .15`)。
- **同时弹出"回溯面板"**,内容:
  - 节点 label + `one_liner`
  - 挂在它上面的 `guards` 徽章
  - **完整上游链路,按层分组、逐层缩进的列表**,一直列到原始字段
  - `refs` 渲染成仓库文件路径文字(**不做链接**,避免把人直接送进代码)
- 再次点击空白处 → 复位。
- 尊重 `prefers-reduced-motion`(和现有代码一致)。

**移动端(站点是移动优先,必须处理):**

- SVG 用 `viewBox` + 双指缩放/拖动(地图式交互,用户可接受)。
- **回溯面板在手机上从底部滑出**,桌面上放右侧。
- 关键取舍:**"一路回溯"这个论点靠面板的列表就能完整传达,不依赖看清图。** 手机上图看不清不影响论点落地。

### 2.7 导出脚本(**一鱼三吃的落地点,不可省略**)

```bash
python platform/export_graph.py --out figures/method_graph.svg
```

- 复用同一套 `graph.py` 布局代码,输出**独立 standalone SVG**(自带尺寸、不依赖页面 CSS,颜色写死;另提供 `--theme light` 出浅色版供论文/PPT 用)。
- **PPT:** PowerPoint 原生支持 SVG,直接插入。
- **论文:** LaTeX 用 `\includegraphics` 需先转一次:
  ```bash
  rsvg-convert -f pdf -o figures/method_graph.pdf figures/method_graph.svg
  # 或 inkscape --export-type=pdf figures/method_graph.svg
  ```
  然后在 `paper/main.tex` 的 §方法 或 §系统架构 插入,补上论文当前缺失的"可解释性"配图。

### 2.8 测试:`tests/test_graph_sync.py`

**方向不对称,这条是壁垒在测试层的体现:**

> **只断言"图上的东西代码里有"(图 ⊆ 代码),不断言反向。** 反向断言等于强制把所有代码实体都上图,直接违反 curation 原则 —— **图允许有意省略,不允许凭空捏造。**

用例:

| 用例 | 断言 |
|---|---|
| `test_graph_parses` | `graph.yaml` 可解析;每条 edge 的 `from`/`to` 都存在于 `nodes`;每个 node 的 `layer` 存在于 `layers` |
| `test_graph_is_dag` | 图无环(否则"回溯"会死循环) |
| `test_operators_subset_of_engine` | 所有 `layer: operator` 且有 `code_symbol` 的节点,其 `code_symbol` ∈ `src.factors.engine.FACTOR_FUNCTIONS` 的键集合 |
| `test_refs_exist` | 每个节点 `refs` 里的路径在仓库中真实存在 |
| `test_layout_deterministic` | 同一份 yaml 连续布局两次,输出 SVG 字符串完全相同 |
| `test_no_factor_expressions` | **`factor` 层节点的 `label`/`one_liner` 不得包含 `(` + 已注册算子名的组合**(粗暴但有效地防止表达式被写进图) |

---

## 3. P2 — 成果展示区(次优先,静态)

### 3.1 定位:诚实的"进行中"陈列

现在没有真结果(合成数据 + mock 因子)。定位为:**方法与系统已就位,真结果在路上**。这对答辩反而是最强的可信度叙事 —— 老师看的是"你有没有一套可信的方法论",不是"你有没有神因子"。

### 3.2 内容源:`platform/content/showcase/*.md`

和 packets 完全一个套路(ADR-0014:内容即仓库文件),`build.py` 编译进单文件。

```yaml
---
id: paper
kind: paper            # paper | system | method-demo | figure | model
order: 10
public: true           # 默认 false;false 的条目 build.py 直接跳过
title: 短论文:可解释 Alpha 因子生成智能体
summary: 一句话说清这份论文在论证什么。
detail_public: false   # 见 §3.3 —— 答辩前为 false
sections:              # kind: paper 专用:章节"菜单"
  - 引言
  - 系统架构
  - 数据契约与点时间对齐
  - 方法(受限表达式引擎 / 基线因子 / 回测指标 / Agent 闭环)
  - 实验:合成数据下的工程验证
  - 可复现性声明
figures:               # 可选:引用已导出的图片
  - results/reports/llm_mock_value_profit_blend/summary.png
---
正文(可选,Markdown 纯文本段落)
```

**`kind` 是通用槽,不为任何具体产物写死 UI。** 用户当前尚未确定"模型"的形态 —— 将来若出现,只需新增一个 `kind: model` 的内容文件,**渲染器零改动**。这是本设计对未来形态不可知(forward-compatible)的关键。

### 3.3 论文卡(已实现 —— 见 ADR-0020 修订)

> **本节的 `detail_public` 闸门方案已作废。** 所有者决定把论文推入公开仓库(理由:需持续追加、需要同学看到进展、真因子与参数留到最后才放)。论文既已公开可读,展示面再藏无意义。

**现行实现(`platform/content/showcase/paper.md`,已上线于 `build.py`):**

- 卡片渲染:`kind` 徽章 + `status`(早期草稿 · 持续追加中)+ `summary` + `note`(合成数据声明)+ 折叠的章节目录 + 链接行。
- **链接直指 GitHub,不把 PDF 拷到服务器:**
  `https://github.com/kyui-azusa/alpha-factor-agent/blob/main/paper/main.pdf`
  仓库是唯一真相源 —— **push 完站点即最新,零同步维护**,不会出现"站上是旧版"。
- 章节目录用原生 `<details>` 折叠:纯叙事节奏,**不承担访问控制**。
- `public` 仍然 fail-closed(默认 `false`),这条不变。

**壁垒退守到真正该守的位置:真实数据上的因子表达式与调好的参数** —— 既不在论文里,也不进仓库。

### 3.4 其余卡片(初版建议三张)

| `kind` | 内容 | 备注 |
|---|---|---|
| `system` | 生成–校验–回测–反馈闭环:LLM 只提假设,数值全由确定性代码产生 | 这是项目最大亮点,应排在最前 |
| `method-demo` | 两个 mock 候选因子跑通完整闭环的**过程**演示 | **必须明标"合成数据示例,非真实因子,IC 数值无经济含义"** |
| `figure` | 基线因子 5 类别 + 回测报告产物示例图 | 只放类别,不放表达式 |

### 3.5 "不全交底"在本方案里的实现 = 纯 UI 折叠

既然壁垒已由 curation 承担(§1),前端的"先藏后露"就**只是叙事节奏**,不承担访问控制:

- 每张卡片默认只展开 `summary`;点"展开"显示 `sections` / 正文。
- **禁止**把 `public: false` 的内容渲染成"模糊占位块" —— 那等于告诉别人"这里有东西",反而招惹。**没有的东西就是不存在,不留痕迹。**

---

## 4. P3 — 工单版本徽章(近乎白送)

用户希望看到"工单对应版本"。**GitHub issues API 的响应里本来就带 `milestone` 字段**,现有 `_compact_issue()` 只是没取出来。

**改动清单(总计不到 20 行):**

1. `platform/intake_service.py` → `_compact_issue()` 增加一行:
   ```python
   "milestone": (item.get("milestone") or {}).get("title"),
   ```
2. `platform/build.py` → `JS` 里 `renderIssues()` 渲染徽章:有 `milestone` 显示 `已在 <milestone> 落地`,无则显示现有的 `处理中`/`已关闭`。
3. **使用约定(写进 `platform/README.md`):** 在 GitHub 建与版本同名的 milestone(如 `v0.3-m3`),**关 issue 时顺手在下拉框选一下**。信息在最准的时刻被记录,零回忆成本。
4. milestone 缺失时**静默降级**(不显示徽章),不得报错。

**为什么这条值得做:** 外部同学提了建议,几天后回来能看到"我提的东西被做进去了"。**这把工单入口从"意见箱"变成"有回响的参与感"** —— 对动机 C(同学分享面)的价值高于展示成果本身。

---

## 5. 明确不做(评审过、被砍,附理由 —— 不要重新提案)

设计过程中这些方案被认真评估过,因"答辩即项目终点"而**全部砍掉**。记录在此以免反复:

| 砍掉的东西 | 砍的理由 |
|---|---|
| **四层 tier 体系**(L1 公开 / L2 微信软门 / L2.5 口令 / L3 永不出) | 权限体系保护的是**未来的持续价值**。项目答辩即终结,没有未来价值可保护。改用 curation(§1),成本为零且更强 |
| **解锁 token / 微信软门 / 口令层** | 同上。且微信软门被识破是伪命题 —— **能拿到网址的人,联系方式你本就有**,收集不到新信息 |
| **版本 manifest + git tag 时间线 + GitHub Contents API 动态加载** | 版本浏览器需要"有很多版本"才有意义。**还剩 3 天,总共可能就 2 个版本** —— 为一条两行的时间线建一整套基础设施,投入产出比极差 |
| **双版本 PDF(public 版 / 完整版)** | 论文全篇合成数据 + mock 因子,对**红线**本就安全,不需要脱敏两份。对**防抄**的处理改用更简单的 `detail_public` 开关(§3.3) |
| **PDF 的 nginx token 校验** | 同上,退化成"传或不传" |
| **从代码自动抽取图节点** | 见 §2.2:规模不值、边抽不出、且会破坏壁垒 |
| **引入 d3 / cytoscape** | 见 §2.5:单文件内联体积不值,且力导向布局会毁掉分层结构 |

---

## 6. 交付切分与验收

**执行顺序严格如下。P1 未验收不得开 P2。**

### P1 知识图谱(目标 ≤ 1 天)
- [ ] `platform/content/graph.yaml` 写出约 40 节点 / 60 边(内容见 §2.4)
- [ ] `platform/graph.py`:`load_graph` / `layout` / `render_svg`,布局确定性
- [ ] `platform/build.py` 接入:图内联进 `dist/index.html`,新增导航入口
- [ ] 交互 JS:点击 → 高亮上游链路 + 回溯面板;移动端底部滑出
- [ ] `platform/export_graph.py`:导出 standalone SVG(深/浅两色)
- [ ] `tests/test_graph_sync.py` 六个用例全过
- [ ] **导出图插入 `paper/main.tex`** 并重新编译通过

**验收:** 打开站点点任一 `metric` 节点(如 ICIR),能看到一条**从 ICIR 一路回溯到原始字段**的完整高亮链路 + 面板列表。在 375px 宽度下面板可读。`pytest tests/test_graph_sync.py` 全绿。

### P2 成果展示区(目标 ≤ 0.5 天)
- [ ] `platform/content/showcase/` 四个内容文件(paper / system / method-demo / figure)
- [ ] `build.py` 渲染器:按 `kind` 决定长相,`public: false` 跳过,默认 fail-closed
- [ ] 论文卡 `detail_public: false`,产物中无 PDF 路径(加单测)
- [ ] 卡片折叠/展开

**验收:** `grep -c "main.pdf\|paper.pdf" platform/dist/index.html` 返回 0。把某内容文件改成 `public: false` 重新构建,产物中**该条目痕迹全无**。

### P3 工单徽章(目标 ≤ 0.5 小时)
- [ ] `_compact_issue()` 加 milestone 字段
- [ ] 前端徽章渲染 + 缺失时静默降级
- [ ] `platform/README.md` 补"关 issue 时选 milestone"的使用约定

**验收:** 给任一已关闭 issue 挂上 milestone,刷新站点历史工单区能看到版本徽章;没挂的不显示徽章也不报错。

### 全局验收
- [ ] `python platform/build.py` 一次通过,产物仍是**单个自包含 `index.html`**(无外部请求)
- [ ] `pytest` 全绿
- [ ] 产物中不含:任何具体因子表达式、参数值、universe 定义、聚源字段清单、PDF 路径(当 `detail_public: false`)

---

## 7. 给 Codex 的注意事项

1. **不要重构 `intake_service.py` 的现有逻辑。** 它已在生产运行。P3 只加一个字段,别动别的。
2. **保持单文件产物。** 不引入外部 CDN、外部字体、外部图片。所有资源内联或 data URI。
3. 风格跟现有代码走:`build.py` 是纯 stdlib + pyyaml,`intake_service.py` 是纯 stdlib。**不要引新依赖。**
4. 中文文案、深色 AI-native 风格、移动优先 —— 与现有站点一致。
5. 若发现本文档与 `CLAUDE.md`「现状」段落矛盾:**以代码为准**。该段落已过时(它说 `src/` 只有空 `__init__.py`,实际 M0–M5 均已实现)。
