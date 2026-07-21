---
id: paper
kind: paper
order: 10
public: true
title: 短论文 · 可解释 Alpha 因子生成智能体
status: 早期草稿 · 持续追加中
summary: >-
  论证一件事:让 LLM 提假设、让确定性代码裁决真伪,因子的"可解释"就能从自然语言的经济故事,
  变成一条可一路回溯到具体字段与有限算子的可审计链路。
note: >-
  当前实验全部跑在合成数据上,只用于验证工程链路(防前视、样本外划分、指标计算、报告落盘)的正确性,
  其中的 IC 数值不具备经济含义,不代表任何真实市场结论。
sections:
  - 引言
  - 相关工作与定位
  - 系统架构
  - 数据契约与点时间对齐
  - 方法(受限表达式引擎 / 基线因子 / 回测指标 / Agent 闭环)
  - 实验:合成数据下的工程验证
  - 可复现性声明
  - 讨论、局限与后续工作
  - 结论
links:
  - label: 在线读 PDF
    href: https://github.com/kyui-azusa/alpha-factor-agent/blob/main/paper/main.pdf
    primary: true
  - label: LaTeX 源码
    href: https://github.com/kyui-azusa/alpha-factor-agent/blob/main/paper/main.tex
  - label: 代码仓库
    href: https://github.com/kyui-azusa/alpha-factor-agent
---
论文与仓库同步更新 —— 这里的链接始终指向最新版本,不存在"网站上是旧版"的问题。
