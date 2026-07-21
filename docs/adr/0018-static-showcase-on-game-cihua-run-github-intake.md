# 0018 — 展示面部署到 alpha.cihua.run,同源工单服务用所有者账号建 issue

日期:2026-07-20
状态:已接受(落实 ADR-0002 / 0017;取代过程中一度尝试的"跳转 GitHub 表单"方案)

## 最终架构

部署在自有 root 权限 nginx 服务器(`root@<SERVER_IP>:<SSH_PORT>`),域名沿用 ADR-0017 的 **`alpha.cihua.run`**:

- **展示面**:单个自包含 `index.html`(深色 AI-native 风格,内联 CSS/JS),`platform/build.py` 生成,放 `/var/www/alpha.cihua.run/`。
- **工单入口**:页面内**结构化表单(问卷星式)**,POST 同源 `/api/intake`。后端 `platform/intake_service.py` 以 systemd 常驻 `127.0.0.1:8791`,nginx 反代 `/api/intake`。后端用**项目所有者的 fine-grained PAT**(server-side,`/etc/alpha/intake.env`,chmod 600)调 GitHub API 建 issue —— **提交者无需 GitHub 账号**,提交人名字写进 issue 正文,`type/priority` → labels(落实 CONTEXT 的 Intake Form/Fields 与 Feedback Issue)。
- 未配置 PAT/REPO 时后端 dry-run(落盘 `/var/log/alpha-intake/dryrun.ndjson`),表单照常可用,便于先上线。

## 服务器落点

| 项 | 路径 |
|---|---|
| 页面 | `/var/www/alpha.cihua.run/index.html` |
| 后端 | `/opt/alpha-intake/intake_service.py` |
| 环境(含 PAT) | `/etc/alpha/intake.env`(600) |
| systemd | `/etc/systemd/system/alpha-intake.service` |
| nginx | `/etc/nginx/conf.d/alpha.cihua.run.conf` |

## 走过的弯路(记录以免反复)

1. 误用面向学生的 `game-student-deploy` skill(只能传静态文件到受限子目录、禁 nginx/后端),据此以为要退到纯静态 + 跳转 GitHub issue 表单、域名退到 `game.cihua.run/<id>/`。
2. 实际应使用 root 权限的 `deploy-static-site` skill,该限制不成立。故回到 ADR-0002/0017 原设计:同源工单服务 + 所有者账号建 issue,域名 `alpha.cihua.run`。

`.github/ISSUE_TEMPLATE/feedback.yml` 保留,供愿意直接在 GitHub 提 issue 的人使用,与页面表单并存。

## 未变的红线

- Result Boundary(ADR-0003)/ Redacted Core:公开仓库与展示面只放方法与思路,不含最终因子表达式、排名或最终指标。
