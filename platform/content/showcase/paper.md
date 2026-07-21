---
id: paper
kind: paper
order: 10
public: true
title: 短论文 · 可解释 Alpha 因子生成智能体
status: 初步实证 · 持续追加中
summary: >-
  论证一件事:让 LLM 提假设、让确定性代码裁决真伪,因子的"可解释"就能从自然语言的经济故事,
  变成一条可一路回溯到具体字段与有限算子的可审计链路。
note: >-
  实验用聚源 JYDB 真实数据(2020–2021),但只覆盖两年、股票池为行情观测构造,
  尚未纳入停牌涨跌停 ST 过滤、行业中性化与完整复权。结果定位为「初步实证与系统验收」,
  不是稳健的 alpha 发现 —— 单次运行不构成跨年份结论。
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
