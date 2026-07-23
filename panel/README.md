# Alpha Research Panel

独立的 Vue 3 静态研究面板,用于演示“业绩预告事件 -> 市场反应”。它与 `platform/` 并列,
共用视觉语言,不共享代码或后端。

## 运行方式

先在仓库根目录导出确定性数据:

```bash
python scripts/export_panel_data.py
```

再构建或预览:

```bash
cd panel
pnpm install
pnpm type-check
pnpm lint
pnpm build
pnpm preview
```

`dist/` 使用相对资源路径,可部署到同域 `/panel/`。答辩主路径只读取构建期 JSON,
P0/P1/P2 和预设问题在断网环境下可用。

## Agent 边界

预设问题完全离线。自由输入是可选增强:用户在本机浏览器配置 OpenAI-compatible
`baseUrl`、`apiKey` 和 `model`,LLM 只把自然语言转换为已有视图参数,不生成市场数值。
未配置或目标服务不支持 CORS 时,不影响任何离线功能。

预设问题和当前自由输入路由完全离线。页面只用确定性规则把研究线索整理为
`ResearchRequest` 草稿,并展示静态候选池、能力预检与预计算证据;它不会调用 LLM,
也不会创建真实运行、保存确认状态或触发回测。

未来可以在新的 ADR 下增加受认证、限流的可选后端,但 LLM 仍只能负责提出想法和读取结果,
回测数值必须继续由确定性代码计算,静态数据与离线演示也必须保留。

## 数据正确性

- 行情先将 `adj_factors.csv` 通过 `merge_asof(direction="backward")` 展开后复权;
- K 线事件标记使用 `publ_date`;
- 任何“若当时买入”语义从下一交易日 `usable_from` 起算;
- 因子导出使用字段白名单,并对表达式和调优参数等禁用字段做断言。
