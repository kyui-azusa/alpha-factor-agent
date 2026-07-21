---
id: 2026-07-20-data-contract
title: 三张表的数据契约:先定协议,再填数据
date: 2026-07-20
tags: [数据契约, 防幸存者偏差]
insight: 在拿到聚源数据前,先把输入表结构写死成契约——尤其把「历史成分股」单列一张表,不然回测会只看今天还活着的股票,天然偏乐观。
visual: |
  prices        date, code, open/high/low/close, vol, amount, adj_factor
  fundamentals  code, report_period, ann_date, <财务字段…>   ← ann_date 用于时间对齐
  universe      date, code                                    ← 历史成分股,防幸存者偏差
                    └── 回测只在「当日在册」的股票上做横截面
follow_up: 你们做 A 股回测时,退市 / 停牌的股票是怎么处理进 universe 的?
---
契约先行:数据后填,但每列含义和 dtype 先定死,避免后期对不上。
