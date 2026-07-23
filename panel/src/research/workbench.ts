import type {
  BacktestabilityCode,
  FactorCandidate,
  ResearchRequest,
  ResearchSource,
  WorkbenchScenario,
} from '@/types/research'

export const DEFAULT_FACTOR_CLUE = '生成一个反映业绩预告文本语气变化的 Alpha 因子，并检验未来 20 日收益'

export const BACKTESTABILITY_LABELS: Record<BacktestabilityCode, string> = {
  currently_backtestable: '当前可回测',
  requires_external_data: '需要外部数据',
  field_missing: '字段缺失',
  mapping_unstable: 'A 股映射不稳定',
  pit_not_verified: 'PIT 未验证',
}

function stableDraftId(value: string): string {
  let hash = 2166136261
  for (const character of value) {
    hash ^= character.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return `draft-${(hash >>> 0).toString(16).padStart(8, '0')}`
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)]
}

function inferRequest(rawClue: string): ResearchRequest {
  const clue = rawClue.trim() || DEFAULT_FACTOR_CLUE
  const asksForText = /文本|语气|措辞|公告|新闻|情绪/.test(clue)
  const asksForExternal = /舆情|社交|微博|搜索|供应链|外部/.test(clue)
  const asksForMinute = /分钟|高频|逐笔|盘口/.test(clue)
  const asksForMacro = /宏观|利率|通胀|政策/.test(clue)
  const asksForIndustry = /行业|板块|产业/.test(clue)
  const signalScope = asksForMacro
    ? 'macro'
    : asksForIndustry
      ? 'industry'
      : asksForExternal
        ? 'mixed'
        : 'company'

  const blockingReasons: BacktestabilityCode[] = []
  if (asksForText) blockingReasons.push('field_missing', 'pit_not_verified')
  if (asksForExternal || asksForMinute) blockingReasons.push('requires_external_data')
  if (asksForMacro || asksForIndustry) blockingReasons.push('mapping_unstable')

  const sources: ResearchSource[] = [
    {
      name: '业绩预告结构化事件',
      kind: 'field' as const,
      status: 'available' as const,
      detail: '预告类型、增长区间、publ_date 与下一交易日 usable_from。',
    },
    {
      name: '日频复权行情',
      kind: 'field' as const,
      status: 'available' as const,
      detail: '静态导出 OHLCV 与复权收益，仅用于确定性计算。',
    },
  ]
  if (asksForText) {
    sources.push({
      name: '公告正文与历史语气特征',
      kind: 'text',
      status: 'missing',
      detail: '当前 panel 导出不包含正文、文本特征或其历史可得时间。',
    })
  }
  if (asksForExternal || asksForMinute) {
    sources.push({
      name: asksForMinute ? '分钟级行情' : '外部舆情源',
      kind: 'external',
      status: 'missing',
      detail: '当前项目未登记该数据源，能力预检必须 fail closed。',
    })
  }
  sources.push({
    name: '公开基线因子结果',
    kind: 'seed',
    status: 'reference',
    detail: '仅作对照证据，真实表达式与调优参数保持脱敏。',
  })

  return {
    rawClue: clue,
    hypothesis: asksForText
      ? '管理层披露语气相对历史的变化可能包含结构化预告幅度之外的增量信息。'
      : '该研究线索可能形成具有横截面差异的公司级可观测信号。',
    signalScope,
    economicPhenomenon: asksForText
      ? '管理层预期与经营信心变化'
      : asksForIndustry
        ? '行业景气度在公司间的传导差异'
        : asksForMacro
          ? '宏观状态变化对公司暴露的异质影响'
          : '公司公开信息变化与后续横截面收益差异',
    observableProxies: asksForText
      ? ['公告语气得分', '相对上次披露的语气变化', '结构化预告幅度中点']
      : ['结构化事件变化', '公开字段的横截面排序'],
    aShareMapping:
      asksForMacro || asksForIndustry
        ? '需要稳定的行业/宏观暴露映射，当前静态数据未覆盖。'
        : 'A 股上市公司 × 交易日面板，公告在 publ_date 后的下一交易日起可用。',
    sources,
    seedReferences: ['质量基线', '动量基线', '低波动基线'],
    target: /60\s*日/.test(clue)
      ? '下一交易日起 60 日收益'
      : /5\s*日/.test(clue)
        ? '下一交易日起 5 日收益'
        : '下一交易日起 20 日收益',
    baseline: '结构化预告字段基线 vs. 结构化字段 + 新信号增量',
    dataMode: 'static_demo',
    backtestability: blockingReasons[0] ?? 'currently_backtestable',
    blockingReasons: unique(blockingReasons),
    draftId: stableDraftId(clue),
    version: 'draft',
    confirmed: false,
  }
}

function candidatesFor(request: ResearchRequest): FactorCandidate[] {
  return [
    {
      id: 'forecast-tone-delta',
      name: '预告语气变化',
      category: '公告文本',
      status: 'unavailable',
      expressionSummary: '文本语气相对公司历史基准的变化摘要',
      sourceSummary: '研究线索 + 公告正文（当前缺失）',
      fields: ['announcement_text', 'ann_date'],
      citations: ['用户研究线索', '公告正文源：未登记'],
      pitRule: '正文必须带原始披露时间；仅 ann_date ≤ T 的文本可进入 T 日特征。',
      synthesis: '公司内历史标准化后做横截面排序。',
      mechanism: '语气变化可能反映管理层对盈利路径的边际判断。',
      expectedDirection: '更积极的语气变化预期对应更高的后续横截面收益。',
      riskExposures: ['公告模板漂移', '行业词汇差异', '文本覆盖偏差'],
      backtestability: request.sources.some((source) => source.name.includes('公告正文'))
        ? 'field_missing'
        : 'requires_external_data',
      rejectionReason: '公告正文与历史时间戳尚未进入静态数据契约，不能标记为当前可回测。',
    },
    {
      id: 'forecast-midpoint-change',
      name: '预告幅度变化代理',
      category: '结构化事件',
      status: 'validated',
      expressionSummary: '预告增长区间中点的公司内变化（窗口参数脱敏）',
      sourceSummary: '结构化预告事件 + PIT 日期边界',
      fields: ['growth_floor', 'growth_ceiling', 'publ_date', 'usable_from'],
      citations: ['panel events 导出契约', 'ADR-0023 PIT 边界'],
      pitRule: '披露日只做事件标记，特征从 usable_from（下一交易日）起生效。',
      synthesis: '以当前可用结构化字段构造文本信号的保守代理。',
      mechanism: '盈利预期区间的边际变化可能反映基本面修正。',
      expectedDirection: '预告改善方向预期为正。',
      riskExposures: ['低覆盖率', '极值预告', '行业周期'],
      backtestability: 'currently_backtestable',
    },
    {
      id: 'quality-reference',
      name: '质量基线对照',
      category: '种子因子',
      status: 'backtested',
      expressionSummary: '公开质量类别基线（表达式与参数脱敏）',
      sourceSummary: '已导出的样本外预计算结果',
      fields: ['公开基线元数据'],
      citations: ['baseline_quality_roe 静态结果', '因子公开字段白名单'],
      pitRule: '沿用确定性回测的字段可得性与日期型样本外划分。',
      synthesis: '作为增量研究的对照，不是本轮生成的新文本因子。',
      mechanism: '盈利质量是与公告语气增量信号比较的基本面基线。',
      expectedDirection: '仅作为对照，不对本轮候选给出买卖结论。',
      riskExposures: ['行业暴露', '规模暴露', '财务字段覆盖'],
      backtestability: 'currently_backtestable',
      evidence: {
        factorId: 'baseline_quality_roe',
        label: '质量基线预计算证据',
        status: 'static_precomputed',
        note: '证据来自静态公开结果，只说明基线表现，不证明本轮文本假设。',
      },
    },
    {
      id: 'future-return-leak',
      name: '未来收益反推语气',
      category: '无效候选',
      status: 'rejected',
      expressionSummary: '使用未来收益选择文本方向',
      sourceSummary: '规则校验拒绝',
      fields: ['future_return_20d'],
      citations: ['PIT 硬约束', '表达式字段白名单'],
      pitRule: '未来收益只能作为标签，禁止进入 T 日因子表达式。',
      synthesis: '无；候选在生成后校验阶段停止。',
      mechanism: '该构造包含目标泄漏，没有可接受的经济解释。',
      expectedDirection: '不适用。',
      riskExposures: ['look-ahead', '目标泄漏'],
      backtestability: 'pit_not_verified',
      rejectionReason: '检测到未来收益字段，违反 PIT 与回测确定性边界。',
    },
    {
      id: 'external-sentiment-confirmation',
      name: '外部舆情确认',
      category: '跨来源',
      status: 'pending',
      expressionSummary: '公告语气与外部舆情方向一致性',
      sourceSummary: '公告文本 + 外部舆情源',
      fields: ['announcement_text', 'external_sentiment'],
      citations: ['跨来源创新策略', '外部源：未登记'],
      pitRule: '两类文本都必须有可审计的历史时间戳与版本。',
      synthesis: '方向一致性和分歧度的候选摘要。',
      mechanism: '公司披露与外部预期的分歧可能包含信息。',
      expectedDirection: '待澄清，不预设方向。',
      riskExposures: ['外部源选择偏差', '时间戳漂移', '覆盖不稳定'],
      backtestability: 'requires_external_data',
      rejectionReason: '保留在候选池等待数据登记；当前不会进入生成或回测。',
    },
  ]
}

export function createWorkbenchScenario(rawClue: string): WorkbenchScenario {
  const request = inferRequest(rawClue)
  return {
    request,
    materials: {
      knowledgeVersion: 'A-share research knowledge v0.1 / static preview',
      dataMode: '静态演示数据；非实时、非任务持久化',
      fields: ['预告类型', '增长区间', 'publ_date', 'usable_from', '日频复权行情'],
      textSources: ['公告正文：未导出', '外部舆情：未登记'],
      seeds: ['质量', '动量', '低波动', '流动性', '价值'],
      operators: ['rank', 'zscore', 'lag', 'delta', 'rolling_mean'],
      hardConstraints: ['PIT 不可关闭', '未来收益仅作标签', '日期型 OOS', '回测禁止 LLM', '未知字段 fail closed'],
    },
    config: {
      count: 5,
      direction: 'both',
      novelty: 'seed_upgrade',
      maxComplexity: 3,
      allowText: true,
      currentlyBacktestableOnly: false,
    },
    candidates: candidatesFor(request),
    preflight: [
      {
        id: 'PF-PIT-001',
        label: 'PIT 与公告可得时间',
        status: request.blockingReasons.includes('pit_not_verified') ? 'blocked' : 'passed',
        evidence: request.blockingReasons.includes('pit_not_verified')
          ? '结构化事件有 usable_from；正文历史时间戳尚无证据。'
          : '结构化事件使用 publ_date / usable_from 双日期契约。',
        suggestion: '登记正文原始披露时间和版本后重新预检。',
      },
      {
        id: 'PF-FIELD-002',
        label: '字段与来源登记',
        status: request.blockingReasons.includes('field_missing') ? 'blocked' : 'passed',
        evidence: request.blockingReasons.includes('field_missing')
          ? '研究所需文本字段未出现在 panel 静态导出。'
          : '所需结构化字段已在静态数据契约中。',
        suggestion: '可先采用预告幅度变化代理，或补齐文本数据管线。',
      },
      {
        id: 'PF-OOS-003',
        label: '日期型样本外划分',
        status: 'passed',
        evidence: '硬约束固定为按日期滚动；不提供随机打乱选项。',
      },
      {
        id: 'PF-RUNTIME-004',
        label: '运行服务与持久化',
        status: 'unverified',
        evidence: '当前页面是离线 schema 演示，未接入 run API 或持久化状态。',
        suggestion: '由 #72/#79/#80 完成真实运行与终局报告后再启用。',
      },
    ],
  }
}
