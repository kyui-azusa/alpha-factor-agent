# AGENTS.md — 项目上下文

这是 **AI金融研学实训营 AI篇 主题四** 的项目:可解释 Alpha 因子生成智能体。

## 你要做什么
按 `docs/BUILD_SPEC.md` 的 Milestone 顺序实现。**先 M0→M3(不含 LLM 的可信底座),再 M4→M6。**

## 当前节奏
现在时间紧、任务重；优先做能落地、能测试、能支撑答辩证据链的最小闭环，不做无关重构。

## 铁律
1. **回测里绝不调用 LLM。** LLM 只负责"提想法/读结果",所有数值由确定性代码计算。
2. **防 look-ahead:** 因子在 T 日只能用 ann_date ≤ T 的数据。这是最重要的正确性约束,`pit_merge` 必须有对应单测。
3. **样本外划分按日期滚动,禁止随机打乱。**
4. 每个 Milestone 写 pytest,过了再进下一个。
5. **省 token:** LLM 调用要缓存、限 max_tokens;能用规则判断的就别用 LLM。

## 关键文档
- 总览与架构:`README.md`
- 实现清单(主要看这个):`docs/BUILD_SPEC.md`
- 数据结构契约:`docs/DATA_SCHEMA.md`(M0 时创建)
- 共享术语与已定决策:`CONTEXT.md` + `docs/adr/`(改方案前先读,不要推翻已定决策)

## 现状
目录骨架已建好,`src/` 下各包只有空 `__init__.py`。从 M0 开始写。
