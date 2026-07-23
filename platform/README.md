# platform —— 想法流展示网站 + 同源工单入口

研究项目的轻量分享面(AI-native 风格,深色 / 白天双主题)。想法卡片从研究过程沉淀而来;工单入口是页面内
**问卷星式结构化表单**,提交后由后端用**项目所有者账号**同步成 GitHub Issue —— 提交者无需 GitHub 账号。

| 决策 | ADR |
|---|---|
| 部署 `alpha.cihua.run`;页面表单 → 同源 `/api/intake` → 所有者账号建 issue | **0018**(落实 0002/0017) |
| 首屏是想法流(feed) | 0008 |
| 想法卡片是仓库 Markdown 内容文件,站点由其生成 | 0014 |
| 只读 + 转发/复制,无点赞评论 | Light Interaction |
| 只分享方法/思路,不含最终因子与结果 | 0003 / Redacted Core |

## 结构

```
platform/
├── content/packets/*.md   想法卡片源文件(YAML frontmatter + 可选正文)
├── static/style.css       样式(移动优先;深/浅两套 token,见下)
├── build.py               生成器 → 单个自包含 dist/index.html(内联 CSS/JS)
├── intake_service.py      工单后端(stdlib;PAT server-side 建 issue/回执,无 token 时 dry-run)
└── uploads/               本地/线上截图落点(线上建议映射到 /var/www/alpha.cihua.run/uploads)
```

## 构建

```bash
python platform/build.py        # → platform/dist/index.html(单文件)
```

## 配色(深 / 浅)

顶栏右上角一枚按钮切换,选择存 `localStorage['alpha-theme']`;**没选过就跟随系统**,白天自动是浅色。
主题在 `<head>` 的一小段脚本里就定好,避免先闪一帧深色。

方法图那一节还有个滚动展开:进场时与版心同宽,滚到它先粘住(`.graph-sticky`),
随滚动把画布推到「整张图刚好放得下」再放行(终点 = `--canvas`,由 `build.py` 按真实布局写入)。
进度写在 `--gx`(0→1)上,由 `GRAPH_JS` 按 `.graph-runway` 的行程算。窄屏 / 矮屏 / reduced-motion 直接给展开态,不粘。

**评价指标不进画布**(`build.py` 的 `OVERLAY_LAYERS`):它与每个因子都相连,画进去是一片蜘蛛网还白占一列。
改成浮在画布右上角的贴片(`.metrics`),点它照样高亮完整上游链路 + 开回溯面板,ADR-0019 的论点不变。
`layout(exclude=...)` 只是不画那一层,**排序仍用完整边集**;`export_graph.py` 不传 exclude,
所以论文/PPT 用的独立 SVG 仍是完整五层(已按逐字节比对确认没变)。
注意 `body` 用的是 `overflow-x: clip` 而非 `hidden` —— `hidden` 会让 body 变成滚动容器,sticky 会失效。

**不要让展开量影响页面高度**,否则临界点上会抽:提示行只切透明度(留位)不切 `display`,
横向滚动条藏掉(经典滚动条在"刚好放得下"处反复出没,每次跳 15px),行程取 `.graph-runway`
而非「track − sticky」。另外几何只在 resize(去抖 120ms)时量,滚动路径纯算术、量化到 1%、两端吸附。

改样式的规矩:**不写字面色,只用 token**(`--ink/--muted/--well/--t1-*/--t2-*/...`),
两套值都在 `style.css` 顶部的 `:root[data-theme="dark"|"light"]` 里。新加颜色要同时补两套。
方法图是内联 SVG,同样吃 `--g-*` token;`export_graph.py` 导出的独立 SVG 仍写死颜色(PPT/论文里没有 CSS)。

## 本地联调后端

```bash
python platform/intake_service.py     # 127.0.0.1:8791,dry-run 落盘
# 配 GITHUB_TOKEN=<PAT> GITHUB_REPO=owner/repo 后即真实建 issue
# 配 INTAKE_ADMIN_TOKEN=<secret> 后可写修复回执
```

## 部署(自有 root nginx 服务器)

站点单文件用 `deploy-static-site` skill 传 `/var/www/alpha.cihua.run/`;后端以 systemd 常驻
`127.0.0.1:8791`,nginx 反代 `/api/intake`。服务器落点见 ADR-0018 表格。要真实建 issue:

```bash
# 服务器上,PAT 只落 /etc/alpha/intake.env(600),绝不进浏览器/仓库
#   GITHUB_TOKEN=github_pat_xxx
#   GITHUB_REPO=kyui-azusa/alpha-factor-agent
#   INTAKE_ADMIN_TOKEN=<long-random-secret>
#   UPLOAD_DIR=/var/www/alpha.cihua.run/uploads
#   PUBLIC_BASE_URL=https://alpha.cihua.run
systemctl restart alpha-intake
curl -s https://alpha.cihua.run/api/intake/health   # {"mode":"github"} 即已切换
```

研究面板由 `panel/` 独立构建并部署到同域 `/panel/`;原站成果区只链接它,不参与其构建:

```bash
cd panel && pnpm build
rsync -a --delete dist/ root@<SERVER_IP>:/var/www/alpha.cihua.run/panel/
```

两套静态产物可以分别回滚。panel 不新增 API,也不改变 `/api/intake` 的反代与服务职责
(ADR-0024)。

## 工单字段 → Issue

Intake Fields(CONTEXT):提交人 / 标题 / 描述 / 类型 / 优先级 / 关联工单 / 需要审核 / 附件 / 截图。
提交人 → 正文;`type/priority` → labels(`功能/缺陷/问题/建议` + `P:高/中/低`);截图保存为公开文件并以 Markdown 图片写入 Issue 正文;防滥用:honeypot + 每 IP 限流 + 5MB 图片上限。

**关联工单**(替代原来的「相关想法卡片」,那栏没人用):新工单可以指着老工单说话。`related_issues` 收自由输入
(`12` / `#12` / `#12, 15`),`parse_related_issues` 去重保序、最多 5 条,写成正文里的 `**关联工单:** #12 #15` ——
GitHub 自己会把 `#12` 变成交叉引用,被引用的工单时间线上出现一条 mention。**刻意不做站内回复/父子层级**:
只有「引用」这一层,复杂度就到此为止。页面上历史工单每条带一枚「引用」按钮(再点一次取消),
点了把号码塞进表单那栏并高亮;手打号码时按钮也会同步显示「已引用」。

**需要审核**(`needs_review`):协作者自己声明「这条还没验证过 —— 比如和 AI 讨论出来的结论」,或希望别人复核。
勾了就打 `待审核` 标签,**同时在正文写一行声明**:标签可能被人在 GitHub 上摘掉,正文那行不会,
所以 `/api/intake/issues` 两边任一成立就算待审核。GitHub 会自己建缺失的标签(仓库里 `prio:低` 就是这么来的);
想要个像样的颜色就先 `gh label create 待审核 -c FBCA04`。

**历史工单筛选**:状态 / 类型 / 提出者 三个下拉 + 「只看待审核」「收起回复」两个开关,
外加默认只露最近 8 条的「展开全部 N 条」。提出者不是 GitHub 作者(那永远是项目账号),
而是后端从正文首行 `**提交人:**` 解析出来的 —— 筛选维度全部挂在 `.issue-item` 的 `data-*` 上,列表本身就是数据源。

## 修复回执 → Issue Comment

修复完成后,后台或自动化可调用受保护的 `POST /api/intake/receipts`,后端会用服务端 PAT 给对应 GitHub Issue 写一条带标记的评论。`/api/intake/issues` 会读取最新评论里的回执摘要,网站“历史工单”列表随刷新同步展示。

回执是**一次仓库级评论查询**(`GET /issues/comments`,倒序翻页,最多 `COMMENTS_MAX_PAGES` 页)按工单号归位的,
不是每条工单发一次请求 —— 列表放开到全量后,后者是几十次串行调用。同一条工单第一次遇到的评论就是最新的,回执优先于普通评论。

```bash
curl -s -X POST https://alpha.cihua.run/api/intake/receipts \
  -H "Authorization: Bearer $INTAKE_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "issue_number": 12,
    "fixed_by": "Codex",
    "summary": "已补充历史工单回执同步。",
    "repair": "新增受保护回执接口,向 GitHub issue 写入带标记的评论。",
    "result": "刷新网站历史工单后可看到最新回执摘要。",
    "close_issue": true
  }'
```

字段要求:`issue_number`、`summary`、`repair`、`result` 必填;`fixed_by` 可选;`close_issue` 为 true 时会在评论成功后关闭对应 Issue。`INTAKE_ADMIN_TOKEN` 只放服务端或自动化环境,不要写入静态站点。

## 新增想法卡片

`content/packets/` 加 `.md`,frontmatter:`id, title, date, tags[], insight, visual, follow_up`。
遵守 Redacted Core,改完重跑 `build.py` 并重新上传。
```
scp -P <SSH_PORT> platform/dist/index.html root@<SERVER_IP>:/var/www/alpha.cihua.run/index.html
```
