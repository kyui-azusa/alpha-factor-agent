---
id: 2026-07-20-lookahead-timeline
title: 一张时间线讲清「防未来数据」
date: 2026-07-20
tags: [防泄漏, point-in-time]
insight: 财报要用「公告日 ann_date」对齐,而不是「报告期 report_period」——T 日的因子只能看见 ann_date ≤ T 的数据,否则就偷看了未来。
visual: |
  报告期 2026Q1 (report_period = 2026-03-31)
        │
        │   真空期:季报还没公布,这段时间不能用 Q1 数据
        ▼
  公告日 ann_date = 2026-04-28  ← 从这天起,因子才允许引用 Q1 财报
        │
        ▼
  可用区间 [ann_date, +∞)  →  pit_merge 只并入 ann_date ≤ 当日 的最新一期
follow_up: 除了财报公告日,你还会给哪些字段单独设「可得日」?(如分析师预期、指数调仓)
---
核心测试:构造一条 ann_date 晚于当日的记录,断言 pit_merge 不会把它并进来。
