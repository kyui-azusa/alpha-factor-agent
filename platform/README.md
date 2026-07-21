# platform —— 想法流展示网站 + 同源工单入口

研究项目的轻量分享面(深色 AI-native 风格)。想法卡片从研究过程沉淀而来;工单入口是页面内
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
├── static/style.css       深色科技风样式(移动优先)
├── build.py               生成器 → 单个自包含 dist/index.html(内联 CSS/JS)
├── intake_service.py      工单后端(stdlib;PAT server-side 建 issue/回执,无 token 时 dry-run)
└── uploads/               本地/线上截图落点(线上建议映射到 /var/www/alpha.cihua.run/uploads)
```

## 构建

```bash
python platform/build.py        # → platform/dist/index.html(单文件)
```

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

## 工单字段 → Issue

Intake Fields(CONTEXT):提交人 / 标题 / 描述 / 类型 / 优先级 / 相关卡片 / 附件 / 截图。
提交人 → 正文;`type/priority` → labels(`功能/缺陷/问题/建议` + `P:高/中/低`);截图保存为公开文件并以 Markdown 图片写入 Issue 正文;防滥用:honeypot + 每 IP 限流 + 5MB 图片上限。

## 修复回执 → Issue Comment

修复完成后,后台或自动化可调用受保护的 `POST /api/intake/receipts`,后端会用服务端 PAT 给对应 GitHub Issue 写一条带标记的评论。`/api/intake/issues` 会读取最新评论里的回执摘要,网站“历史工单”列表随刷新同步展示。

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
