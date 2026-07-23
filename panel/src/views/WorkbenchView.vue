<script setup lang="ts">
import {
  AlertTriangle,
  ArrowRight,
  Ban,
  BookOpen,
  CheckCircle2,
  CircleDot,
  Clock3,
  Database,
  ExternalLink,
  FileSearch,
  FileText,
  FlaskConical,
  Layers3,
  LockKeyhole,
  Play,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  TestTube2,
} from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import SimpleLineChart from '@/components/SimpleLineChart.vue'
import {
  BACKTESTABILITY_LABELS,
  createWorkbenchScenario,
  DEFAULT_FACTOR_CLUE,
} from '@/research/workbench'
import { useMarketStore } from '@/stores/market'
import type { FactorResult } from '@/types/market'
import type { CandidateStatus, FactorCandidate, PreflightItem } from '@/types/research'

const route = useRoute()
const router = useRouter()
const market = useMarketStore()
const rawClue = computed(() =>
  typeof route.query.clue === 'string' && route.query.clue.trim()
    ? route.query.clue.trim()
    : DEFAULT_FACTOR_CLUE,
)
const scenario = computed(() => createWorkbenchScenario(rawClue.value))
const selectedId = ref('forecast-tone-delta')
const evidence = ref<FactorResult | null>(null)
const evidenceError = ref('')
const candidateCount = ref(5)
const direction = ref<'both' | 'positive' | 'negative'>('both')
const novelty = ref<'seed_upgrade' | 'cross_source' | 'conservative'>('seed_upgrade')
const maxComplexity = ref(3)
const allowText = ref(true)
const backtestableOnly = ref(false)

const selected = computed<FactorCandidate>(() =>
  scenario.value.candidates.find((candidate) => candidate.id === selectedId.value) ??
  scenario.value.candidates[0]!,
)
const blockers = computed(() => scenario.value.preflight.filter((item) => item.status === 'blocked'))
const statusCounts = computed(() =>
  scenario.value.candidates.reduce<Record<CandidateStatus, number>>(
    (counts, candidate) => {
      counts[candidate.status] += 1
      return counts
    },
    { pending: 0, validated: 0, rejected: 0, unavailable: 0, backtested: 0 },
  ),
)
const evidenceSeries = computed(() => [
  { label: 'Rank IC', color: '#e5b85c', points: evidence.value?.ic_series ?? [] },
])
const meanIc = computed(() => {
  const points = evidence.value?.ic_series ?? []
  return points.length ? points.reduce((sum, point) => sum + point.value, 0) / points.length : null
})

const statusMeta: Record<CandidateStatus, { label: string; icon: typeof CircleDot }> = {
  pending: { label: '待校验', icon: Clock3 },
  validated: { label: '校验通过', icon: CheckCircle2 },
  rejected: { label: '已拒绝', icon: Ban },
  unavailable: { label: '不可回测', icon: AlertTriangle },
  backtested: { label: '已有证据', icon: TestTube2 },
}

const preflightLabels: Record<PreflightItem['status'], string> = {
  passed: '通过',
  blocked: '阻断',
  unverified: '未检验',
  external: '外部假设',
}

watch(
  () => selected.value.evidence?.factorId,
  async (factorId) => {
    evidence.value = null
    evidenceError.value = ''
    if (!factorId) return
    try {
      await market.initialize()
      evidence.value = await market.loadFactor(factorId)
    } catch (cause) {
      evidenceError.value = cause instanceof Error ? cause.message : '静态证据读取失败'
    }
  },
  { immediate: true },
)

onMounted(() => market.initialize())

function selectCandidate(candidate: FactorCandidate) {
  selectedId.value = candidate.id
}

function resetConfig() {
  const defaults = scenario.value.config
  candidateCount.value = defaults.count
  direction.value = defaults.direction
  novelty.value = defaults.novelty
  maxComplexity.value = defaults.maxComplexity
  allowText.value = defaults.allowText
  backtestableOnly.value = defaults.currentlyBacktestableOnly
}

function startNewClue() {
  router.push('/')
}
</script>

<template>
  <section class="workbench-view">
    <header class="workbench-heading">
      <div>
        <div class="eyebrow"><FlaskConical :size="14" /> 因子生成工作台</div>
        <h1>{{ scenario.request.economicPhenomenon }}</h1>
        <p>{{ scenario.request.rawClue }}</p>
      </div>
      <div class="demo-state"><LockKeyhole :size="14" /> 静态合同预览 · 未创建运行</div>
    </header>

    <ol class="workflow-rail" aria-label="研究流程">
      <li class="active"><BookOpen :size="15" /><span>生成材料</span></li>
      <li class="active"><SlidersHorizontal :size="15" /><span>生成参数</span></li>
      <li class="active"><Layers3 :size="15" /><span>候选池</span></li>
      <li class="active"><FileSearch :size="15" /><span>来源卡</span></li>
      <li><ShieldCheck :size="15" /><span>校验状态</span></li>
      <li><TestTube2 :size="15" /><span>回测证据</span></li>
      <li><RotateCcw :size="15" /><span>反馈迭代</span></li>
    </ol>

    <section class="request-contract" aria-labelledby="request-contract-title">
      <header>
        <div>
          <span class="section-kicker">RESEARCH REQUEST · {{ scenario.request.draftId }}</span>
          <h2 id="request-contract-title">研究线索已整理为草稿合同</h2>
        </div>
        <span class="contract-state"><Clock3 :size="13" /> 待确认</span>
      </header>
      <div class="request-chain">
        <div><span>经济现象</span><strong>{{ scenario.request.economicPhenomenon }}</strong></div>
        <ArrowRight :size="15" />
        <div><span>可观测代理</span><strong>{{ scenario.request.observableProxies.join(' / ') }}</strong></div>
        <ArrowRight :size="15" />
        <div><span>A 股映射</span><strong>{{ scenario.request.aShareMapping }}</strong></div>
        <ArrowRight :size="15" />
        <div><span>预测目标</span><strong>{{ scenario.request.target }}</strong></div>
      </div>
      <dl class="request-details">
        <div><dt>研究假设</dt><dd>{{ scenario.request.hypothesis }}</dd></div>
        <div><dt>信号层级</dt><dd>{{ scenario.request.signalScope }}</dd></div>
        <div><dt>对照方案</dt><dd>{{ scenario.request.baseline }}</dd></div>
        <div><dt>合同状态</dt><dd>draft v0 · 未确认 · 不可进入真实运行</dd></div>
      </dl>
    </section>

    <section class="preflight-strip" :class="{ blocked: blockers.length }" aria-label="能力预检摘要">
      <div class="preflight-summary">
        <AlertTriangle v-if="blockers.length" :size="18" />
        <CheckCircle2 v-else :size="18" />
        <div>
          <strong>{{ blockers.length ? `${blockers.length} 项阻断，候选不会进入真实运行` : '静态预检未发现阻断项' }}</strong>
          <span>关键证明缺失时 fail closed；修改任务后必须重新预检。</span>
        </div>
      </div>
      <div class="preflight-items">
        <div v-for="item in scenario.preflight" :key="item.id" :class="`is-${item.status}`">
          <span>{{ item.id }} · {{ preflightLabels[item.status] }}</span>
          <strong>{{ item.label }}</strong>
          <small>{{ item.evidence }}</small>
        </div>
      </div>
    </section>

    <div class="workbench-setup">
      <section class="materials-panel" aria-labelledby="materials-title">
        <header>
          <div><span class="section-kicker">01 · MATERIALS</span><h2 id="materials-title">本轮生成材料</h2></div>
          <Database :size="17" />
        </header>
        <dl class="materials-list">
          <div><dt>知识版本</dt><dd>{{ scenario.materials.knowledgeVersion }}</dd></div>
          <div><dt>数据模式</dt><dd>{{ scenario.materials.dataMode }}</dd></div>
          <div><dt>可用字段</dt><dd><span v-for="field in scenario.materials.fields" :key="field">{{ field }}</span></dd></div>
          <div><dt>文本源</dt><dd><span v-for="source in scenario.materials.textSources" :key="source" class="warning-chip">{{ source }}</span></dd></div>
          <div><dt>种子因子</dt><dd><span v-for="seed in scenario.materials.seeds" :key="seed">{{ seed }}</span></dd></div>
          <div><dt>允许算子</dt><dd><code v-for="operator in scenario.materials.operators" :key="operator">{{ operator }}</code></dd></div>
          <div class="hard-constraints"><dt>硬约束</dt><dd><span v-for="rule in scenario.materials.hardConstraints" :key="rule"><LockKeyhole :size="11" />{{ rule }}</span></dd></div>
        </dl>
      </section>

      <section class="generation-panel" aria-labelledby="generation-title">
        <header>
          <div><span class="section-kicker">02 · GENERATION</span><h2 id="generation-title">生成参数</h2></div>
          <button type="button" class="icon-action" title="恢复默认生成参数" @click="resetConfig"><RotateCcw :size="15" /></button>
        </header>
        <div class="generation-controls">
          <label>
            <span>候选数量 <b>{{ candidateCount }}</b></span>
            <input v-model.number="candidateCount" type="range" min="3" max="8" step="1" />
          </label>
          <fieldset>
            <legend>预期方向</legend>
            <div class="segmented-control">
              <button type="button" :class="{ active: direction === 'both' }" @click="direction = 'both'">双向</button>
              <button type="button" :class="{ active: direction === 'positive' }" @click="direction = 'positive'">正向</button>
              <button type="button" :class="{ active: direction === 'negative' }" @click="direction = 'negative'">反向</button>
            </div>
          </fieldset>
          <label>
            <span>创新方式</span>
            <select v-model="novelty">
              <option value="seed_upgrade">种子升级</option>
              <option value="cross_source">跨来源组合</option>
              <option value="conservative">保守代理</option>
            </select>
          </label>
          <label>
            <span>复杂度上限 <b>{{ maxComplexity }}</b></span>
            <input v-model.number="maxComplexity" type="range" min="1" max="5" step="1" />
          </label>
          <label class="toggle-row">
            <span><b>允许文本特征</b><small>缺少文本管线时保留为不可回测候选</small></span>
            <input v-model="allowText" type="checkbox" />
          </label>
          <label class="toggle-row">
            <span><b>仅执行当前可回测项</b><small>候选池仍保留拒绝与阻断记录</small></span>
            <input v-model="backtestableOnly" type="checkbox" />
          </label>
        </div>
        <button type="button" class="run-button" disabled title="真实运行 API 尚未接入">
          <Play :size="15" /> 运行不可用 · 静态演示
        </button>
      </section>
    </div>

    <section class="candidate-section" aria-labelledby="candidate-title">
      <header class="candidate-heading">
        <div><span class="section-kicker">03 · CANDIDATE POOL</span><h2 id="candidate-title">候选因子池</h2></div>
        <div class="candidate-counts">
          <span><i class="validated"></i>{{ statusCounts.validated }} 通过</span>
          <span><i class="rejected"></i>{{ statusCounts.rejected }} 拒绝</span>
          <span><i class="unavailable"></i>{{ statusCounts.unavailable + statusCounts.pending }} 待补证据</span>
          <span><i class="backtested"></i>{{ statusCounts.backtested }} 有基线证据</span>
        </div>
      </header>

      <div class="candidate-workspace">
        <div class="candidate-table-wrap">
          <table class="candidate-table">
            <thead><tr><th>候选</th><th>类别</th><th>来源摘要</th><th>可回测状态</th><th>流转状态</th></tr></thead>
            <tbody>
              <tr
                v-for="candidate in scenario.candidates"
                :key="candidate.id"
                :class="{ selected: selected.id === candidate.id }"
                tabindex="0"
                @click="selectCandidate(candidate)"
                @keydown.enter="selectCandidate(candidate)"
              >
                <td><strong>{{ candidate.name }}</strong><small>{{ candidate.expressionSummary }}</small></td>
                <td>{{ candidate.category }}</td>
                <td>{{ candidate.sourceSummary }}</td>
                <td><span :class="`backtestability is-${candidate.backtestability}`">{{ BACKTESTABILITY_LABELS[candidate.backtestability] }}</span></td>
                <td><span :class="`candidate-status is-${candidate.status}`"><component :is="statusMeta[candidate.status].icon" :size="13" />{{ statusMeta[candidate.status].label }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>

        <aside class="candidate-inspector" aria-live="polite">
          <header>
            <div><span class="section-kicker">SOURCE CARD · {{ selected.id }}</span><h3>{{ selected.name }}</h3></div>
            <span :class="`candidate-status is-${selected.status}`"><component :is="statusMeta[selected.status].icon" :size="13" />{{ statusMeta[selected.status].label }}</span>
          </header>

          <div v-if="selected.rejectionReason" class="candidate-decision" :class="`is-${selected.status}`">
            <AlertTriangle :size="15" />
            <span><strong>{{ selected.status === 'rejected' ? '停止原因' : '当前限制' }}</strong>{{ selected.rejectionReason }}</span>
          </div>

          <dl class="source-card">
            <div><dt>表达式摘要</dt><dd>{{ selected.expressionSummary }}</dd></div>
            <div><dt>字段</dt><dd><code v-for="field in selected.fields" :key="field">{{ field }}</code></dd></div>
            <div><dt>来源引用</dt><dd><span v-for="citation in selected.citations" :key="citation"><FileText :size="12" />{{ citation }}</span></dd></div>
            <div><dt>PIT 规则</dt><dd>{{ selected.pitRule }}</dd></div>
            <div><dt>合成方式</dt><dd>{{ selected.synthesis }}</dd></div>
            <div><dt>经济机制</dt><dd>{{ selected.mechanism }}</dd></div>
            <div><dt>预期方向</dt><dd>{{ selected.expectedDirection }}</dd></div>
            <div><dt>风险暴露</dt><dd><span v-for="risk in selected.riskExposures" :key="risk">{{ risk }}</span></dd></div>
          </dl>

          <section v-if="selected.evidence" class="evidence-card">
            <header>
              <div><span class="section-kicker">STATIC EVIDENCE</span><h4>{{ selected.evidence.label }}</h4></div>
              <span><Database :size="12" /> 预计算</span>
            </header>
            <p>{{ selected.evidence.note }}</p>
            <div v-if="evidenceError" class="evidence-error">{{ evidenceError }}</div>
            <template v-else-if="evidence">
              <div class="evidence-metrics">
                <div><span>平均 Rank IC</span><strong>{{ meanIc?.toFixed(3) ?? '—' }}</strong></div>
                <div><span>证据口径</span><strong>样本外静态结果</strong></div>
              </div>
              <SimpleLineChart :series="evidenceSeries" value-format="percent" zero-line />
              <button type="button" @click="router.push(`/factors?factor=${selected.evidence?.factorId}`)">
                查看完整基线证据 <ExternalLink :size="13" />
              </button>
            </template>
          </section>
        </aside>
      </div>
    </section>

    <footer class="workbench-footer">
      <p><ShieldCheck :size="14" /> 本页只展示研究合同、规则判断与静态预计算证据，不构成投资建议。</p>
      <button type="button" @click="startNewClue">返回聊天输入新线索</button>
    </footer>
  </section>
</template>
