<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { LoaderCircle } from '@lucide/vue'

import PortfolioBuilder from '@/components/PortfolioBuilder.vue'
import SimpleLineChart from '@/components/SimpleLineChart.vue'
import { useMarketStore } from '@/stores/market'
import { usePortfolioStore } from '@/stores/portfolio'
import type { BenchmarkData, StockData } from '@/types/market'
import { buildPortfolioResult } from '@/utils/portfolio'

const market = useMarketStore()
const portfolio = usePortfolioStore()
const loadedStocks = ref<StockData[]>([])
const benchmark = ref<BenchmarkData | null>(null)
const loading = ref(false)
const error = ref('')

const result = computed(() =>
  buildPortfolioResult(loadedStocks.value, portfolio.normalizedWeights, benchmark.value),
)
const chartSeries = computed(() => [
  { label: '当前组合', color: '#45c7d8', points: result.value.nav },
  { label: benchmark.value?.label ?? '样本股票等权基准', color: '#7f899b', points: result.value.benchmark },
])
const stats = computed(() => [
  { label: '区间收益', value: formatPercent(result.value.totalReturn) },
  { label: '年化波动', value: formatPercent(result.value.annualVolatility) },
  { label: '最大回撤', value: formatPercent(result.value.maxDrawdown) },
  { label: '夏普比率', value: result.value.sharpe?.toFixed(2) ?? '—' },
])

function formatPercent(value: number | null): string {
  return value === null ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}

async function refresh() {
  if (!portfolio.codes.length) {
    loadedStocks.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    loadedStocks.value = await Promise.all(portfolio.codes.map((code) => market.loadStock(code)))
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '组合数据读取失败'
  } finally {
    loading.value = false
  }
}

watch(() => [...portfolio.codes], refresh)
onMounted(async () => {
  await market.initialize()
  if (!portfolio.codes.length) {
    const defaults = [...market.selectedCodes, ...market.stocks.slice(0, 3).map((stock) => stock.code)]
    portfolio.setCodes([...new Set(defaults)].slice(0, 3))
  }
  benchmark.value = await market.loadBenchmark()
  await refresh()
})
</script>

<template>
  <section>
    <header class="view-header">
      <div>
        <h1>组合研究</h1>
        <p>本地收益序列在浏览器内按交易日对齐、归一化权重并即时加权。</p>
      </div>
    </header>

    <div v-if="error" class="state-message error-state">{{ error }}</div>
    <div v-else class="portfolio-layout">
      <PortfolioBuilder
        :stocks="market.stocks"
        :codes="portfolio.codes"
        :mode="portfolio.mode"
        :raw-weights="portfolio.rawWeights"
        :normalized-weights="portfolio.normalizedWeights"
        @add="portfolio.addCode"
        @remove="portfolio.removeCode"
        @update:mode="portfolio.mode = $event"
        @weight="portfolio.setWeight"
      />

      <div class="portfolio-results">
        <div class="metric-strip">
          <div v-for="stat in stats" :key="stat.label">
            <span>{{ stat.label }}</span>
            <strong>{{ stat.value }}</strong>
          </div>
        </div>
        <div class="research-panel nav-panel">
          <header>
            <div><strong>组合净值</strong><small>{{ result.nav.length }} 个共同交易日</small></div>
            <span>初始净值 1.00</span>
          </header>
          <div v-if="loading" class="state-message inner-state"><LoaderCircle class="spin" :size="20" /></div>
          <SimpleLineChart v-else :series="chartSeries" />
        </div>
      </div>
    </div>
    <p class="pit-note">组合只使用导出的复权收益率；基准在 Python 导出阶段按样本股票等权预计算。</p>
  </section>
</template>
