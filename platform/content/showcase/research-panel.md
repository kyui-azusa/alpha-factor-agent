---
id: research-panel
kind: method-demo
order: 5
public: true
title: 研究面板 · 业绩预告事件 → 市场反应
status: 答辩演示 · 断网可用
summary: >-
  选一只股票,把业绩预告披露日标在复权 K 线上,再观察下一交易日起的市场反应;
  也可以构建组合、浏览公开基线因子结果,或用预设问题切换研究视图。
note: >-
  所有市场数值由 Python 在构建期确定性计算并导成 JSON。披露标记使用 publ_date,
  “若当时买入”只从 usable_from 起算;真实因子表达式与调优参数不进入公开产物。
links:
  - label: 打开研究面板
    href: /panel/
    primary: true
  - label: 架构决策
    href: https://github.com/kyui-azusa/alpha-factor-agent/blob/main/docs/adr/0023-research-panel-as-separate-static-surface.md
---
研究面板与想法流独立构建、独立部署。原站只提供入口,不共享组件,也不依赖 panel 的运行状态。
