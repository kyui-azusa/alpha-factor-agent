<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { LoaderCircle, ShieldCheck } from '@lucide/vue'
import { useRoute } from 'vue-router'

import SimpleLineChart from '@/components/SimpleLineChart.vue'
import { useMarketStore } from '@/stores/market'
import type { FactorResult } from '@/types/market'

const market = useMarketStore()
const route = useRoute()
const activeId = ref('')
const factor = ref<FactorResult | null>(null)
const loading = ref(false)
const error = ref('')

const icSeries = computed(() => [
  { label: 'Rank IC', color: '#e5b85c', points: factor.value?.ic_series ?? [] },
])
const navSeries = computed(() => [
  { label: '多空净值', color: '#43c98d', points: factor.value?.long_short_nav ?? [] },
])
const quantiles = computed(() =>
  Object.entries(factor.value?.quantile_returns ?? {}).sort(([left], [right]) => left.localeCompare(right)),
)
const maxQuantile = computed(() => Math.max(...quantiles.value.map(([, value]) => Math.abs(value)), 0.001))
const meanIc = computed(() => {
  const values = factor.value?.ic_series.map((point) => point.value) ?? []
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
})

async function refresh(id: string) {
  if (!id) return
  loading.value = true
  error.value = ''
  try {
    factor.value = await market.loadFactor(id)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '因子结果读取失败'
  } finally {
    loading.value = false
  }
}

watch(activeId, refresh)
watch(
  () => route.query.factor,
  (factorId) => {
    if (
      typeof factorId === 'string' &&
      market.manifest?.factors.some((item) => item.id === factorId)
    ) {
      activeId.value = factorId
    }
  },
)
onMounted(async () => {
  await market.initialize()
  const requested = typeof route.query.factor === 'string' ? route.query.factor : ''
  activeId.value = market.manifest?.factors.some((item) => item.id === requested)
    ? requested
    : (market.manifest?.factors[0]?.id ?? '')
})
</script>

<template>
  <section>
    <header class="view-header">
      <div>
        <h1>因子结果</h1>
        <p>样本外预计算结果浏览，仅公开类别标签与图表。</p>
      </div>
      <div class="redaction-badge"><ShieldCheck :size="15" /> 已脱敏</div>
    </header>

    <div class="factor-tabs" role="tablist" aria-label="因子类别">
      <button
        v-for="item in market.manifest?.factors"
        :key="item.id"
        type="button"
        :class="{ active: activeId === item.id }"
        @click="activeId = item.id"
      >
        <span>{{ item.label }}</span><small>{{ item.category }}</small>
      </button>
    </div>

    <div v-if="error" class="state-message error-state">{{ error }}</div>
    <div v-else-if="loading || !factor" class="state-message"><LoaderCircle class="spin" :size="20" /></div>
    <template v-else>
      <div class="factor-summary">
        <div><span>公开名称</span><strong>{{ factor.label }}</strong></div>
        <div><span>类别</span><strong>{{ factor.category }}</strong></div>
        <div><span>平均 Rank IC</span><strong>{{ meanIc?.toFixed(3) ?? '—' }}</strong></div>
        <div><span>观测期</span><strong>{{ factor.ic_series[0]?.date }} — {{ factor.ic_series[factor.ic_series.length - 1]?.date }}</strong></div>
      </div>

      <div class="factor-grid">
        <div class="research-panel">
          <header><div><strong>IC 序列</strong><small>样本外 Rank IC</small></div></header>
          <SimpleLineChart :series="icSeries" value-format="percent" zero-line />
        </div>
        <div class="research-panel quantile-panel">
          <header><div><strong>分组收益</strong><small>预计算均值</small></div></header>
          <div class="quantile-bars">
            <div v-for="[label, value] in quantiles" :key="label">
              <span>{{ label.toUpperCase() }}</span>
              <i><b :style="{ height: `${Math.max(4, Math.abs(value) / maxQuantile * 100)}%` }"></b></i>
              <strong>{{ (value * 100).toFixed(2) }}%</strong>
            </div>
          </div>
        </div>
        <div class="research-panel factor-nav-panel">
          <header><div><strong>多空净值</strong><small>预计算序列</small></div></header>
          <SimpleLineChart :series="navSeries" />
        </div>
      </div>
      <p class="pit-note">公开面板不包含真实数据上的最终因子表达式、窗口、阈值、权重或其他调优参数。</p>
    </template>
  </section>
</template>
