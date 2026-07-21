# 交接给 Codex — 2026-07-20 进度总结

Claude 这边只做了 **platform/**(展示网站 + 工单入口),已上线验证。**研究主线(M0–M6,`src/` 全部)还没开工**,这部分请 Codex 接手,按 `docs/BUILD_SPEC.md` 顺序做。

---

## 已完成:platform/(展示网站 + 工单入口)

**线上地址:** https://alpha.cihua.run/(HTTPS,证书到 2026-10-18,自动续期)
**反馈仓库:** https://github.com/kyui-azusa/alpha-factor-agent(公开,目前只放了工单用的 README + issue 模板)

### 做了什么

- 单文件自包含 `index.html`(深色 AI-native 风格,首屏想法流,内联 CSS/JS),由 `platform/build.py` 从 `platform/content/packets/*.md` 生成。已放 4 张开篇卡片(路线图、防未来数据时间线、数据契约、样本外划分)。
- 页面内问卷星式工单表单 → 同源 `POST /api/intake` → 后端 `platform/intake_service.py`(stdlib,systemd 常驻 `127.0.0.1:8791`)→ 用项目所有者账号建 GitHub issue。**已用真实提交验证过两次(issue #1、#2,均已关闭)**,提交者不需要 GitHub 账号。
- 服务器(`root@<SERVER_IP>:<SSH_PORT>`,root 权限自有 nginx):
  - 页面 `/var/www/alpha.cihua.run/index.html`
  - 后端 `/opt/alpha-intake/intake_service.py`,env `/etc/alpha/intake.env`(600,含 GITHUB_TOKEN/REPO)
  - systemd unit `alpha-intake.service`(`enabled`,重启机器会自动拉起)
  - nginx `/etc/nginx/conf.d/alpha.cihua.run.conf`(含 `/api/intake` 反代 + HTTPS 跳转)
- 决策记录:`docs/adr/0018-static-showcase-on-game-cihua-run-github-intake.md`。用法见 `platform/README.md`。

### 已知待办 / 风险(留给人或 Codex 决定,不要擅自处理)

1. **`/etc/alpha/intake.env` 里的 GITHUB_TOKEN 是本机 `gh` 的 OAuth token(scope 偏宽:`repo`)**,不是最小权限的 fine-grained PAT。应换成仅 `kyui-azusa/alpha-factor-agent` 仓库、仅 Issues 读写的 PAT。换的时候在服务器上改 `/etc/alpha/intake.env` 后 `systemctl restart alpha-intake`,别的都不用动。
2. **公开仓库 `kyui-azusa/alpha-factor-agent` 目前只放了工单壳**(README + `.github/ISSUE_TEMPLATE/`),**没有推送完整研究代码**。CONTEXT.md 里定的 Result Boundary(ADR-0003)/ Redacted Core 要求:最终因子表达式、排名、最终指标表、原始聚源数据、敏感字段细节不能进公开仓库。哪些内容能推、哪些要留在私仓,需要用户本人决定,不要自作主张推送。
3. 想法卡片(`platform/content/packets/*.md`)目前都是"开篇卡"(工程路线,不含结果)。以后每天按 CONTEXT.md 的 *Idea Packet* / *Packet Source Priority* 定义追加,遵守 Redacted Core:不放真实因子表达式、排名、最终指标。
4. **对外文案避坑**:页面文案已经改过两轮 —— 不要在页面/README 上明文写"这是脱敏的""不含最终结果""打码/伪公式"之类的话,那是内部准则,写出来反而暴露策略。该藏的东西就不放上去,不用解释为什么不放。

### 更新页面的方法

```bash
python platform/build.py                    # → platform/dist/index.html(单文件)
scp -P <SSH_PORT> platform/dist/index.html root@<SERVER_IP>:/var/www/alpha.cihua.run/index.html
```

---

## 未开工:研究主线(`src/` 全部,M0–M6)

`src/` 下所有包目前只有空 `__init__.py`,**M0 都还没开始**。按 `docs/BUILD_SPEC.md` 的顺序做,`CLAUDE.md`/`AGENTS.md` 有铁律和架构概览,先读那两个。

**执行顺序:** M0 配置+数据契约 → M1 数据管线 → M2 因子引擎+基线 → M3 回测(纯代码)→ M4 LLM 封装 → M5 三 Agent 闭环 → M6 汇总可解释性。

**先把 M0–M3 做扎实(不涉及 LLM),这是可信底座;M4–M5 才引入 LLM。**

### 铁律(不可违反,详见 CLAUDE.md)

1. 回测里绝不调用 LLM。
2. 防 look-ahead:因子在 T 日只能用 `ann_date ≤ T` 的数据,`pit_merge` 必须有单测。
3. 样本外划分按日期滚动,禁止随机打乱。
4. 每个 Milestone 写 pytest,过了再进下一个。
5. LLM 调用要缓存、限 max_tokens。

### 立即可做的第一步(M0)

- `src/config.py`:全局配置(`freq`, `universe`, `start_date`, `end_date`, `train_end`, `cost_bps`, `data_dir`, `results_dir`)。
- `docs/DATA_SCHEMA.md`(**还不存在,需新建**):定义 `prices` / `fundamentals`(含 `ann_date`)/ `universe` 三张表结构。

具体到每个 Milestone 的文件、函数签名、验收标准,`docs/BUILD_SPEC.md` 已经写全了,照做即可。改方案前先读 `CONTEXT.md` + `docs/adr/`,里面的已定决策不要推翻。

### 五天冲刺节奏

截止约 2026-07-24/25。M0–M3 必须真实且有测试,M4–M5 可轻量或按需 mock,M6 出答辩/论文材料(defense bundle:短论文 + 答辩 slides + 可复现代码包,见 ADR-0009/0010)。
