---
id: paper
kind: paper
order: 10
public: true
title: 短论文 · 可解释 Alpha 因子生成智能体
status: 初步实证 · 持续追加中
summary: >-
  问一个可证伪的问题:当结构化数据已经公开了同一事件的关键数字时,LLM 读文本还能多告诉我们什么?
  以 A 股业绩预告为检验场,让 LLM 提假设、让确定性代码裁决真伪 —— 增量存在与否,两个方向都是结论。
note: >-
  实验用聚源 JYDB 真实数据,窗口已由 2020–2021 扩至 2015–2021。此前版本存在两处已修正的缺陷:
  复权因子被写死为 1.0(价格实为未复权),以及缺少行业分类因而无法做行业中性化。
  统计口径改用 Newey-West 修正 t 值 —— 持有期重叠会把朴素 t 值高估三到四倍(实测 5.93 → 1.60)。
  尚未纳入停牌涨跌停 ST 过滤。结果定位为「初步实证与系统验收」,不是稳健的 alpha 发现。
sections:
  - 引言
  - 相关工作与定位
  - 系统架构
  - 数据契约与点时间对齐
  - 方法(受限表达式引擎 / 基线因子 / 回测指标 / Agent 闭环)
  - 实验:聚源真实数据下的初步实证
  - 可复现性声明
  - 讨论、局限与后续工作
  - 结论
snapshot:
  src: paper/main.pdf
  as: paper.pdf
links:
  - label: 站内阅读
    href: /paper.pdf
    primary: true
    stamp: snapshot
    mode: embed
  - label: 仓库最新版
    href: https://github.com/kyui-azusa/alpha-factor-agent/blob/main/paper/main.pdf
  - label: LaTeX 源码
    href: https://github.com/kyui-azusa/alpha-factor-agent/blob/main/paper/main.tex
  - label: 代码仓库
    href: https://github.com/kyui-azusa/alpha-factor-agent
---
站内是我选定的快照版本;论文在仓库里持续追加,想看最新进展的直接进仓库。
