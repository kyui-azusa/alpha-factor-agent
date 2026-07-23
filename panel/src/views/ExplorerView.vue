<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { CalendarClock, Database, LoaderCircle } from '@lucide/vue'

import KLineChart from '@/components/KLineChart.vue'
import ReturnStats from '@/components/ReturnStats.vue'
import StockPicker from '@/components/StockPicker.vue'
import { useMarketStore } from '@/stores/market'
import type { ChartRange, StockData } from '@/types/market'
import { sliceStock } from '@/utils/market'

const market = useMarketStore()
const stock = ref<StockData | null>(null)
const stockLoading = ref(false)
const ranges: Array<{ value: ChartRange; label: string }> = [
  { value: '1m', label: '近 1 月' },
  { value: '3m', label: '近 3 月' },
  { value: '1y', label: '近 1 年' },
  { value: 'all', label: '全部' },
]

const visibleStock = computed(() =>
  stock.value ? sliceStock(stock.value, market.explorerRange) : null,
)
const visibleEvents = computed(() => {
  const current = visibleStock.value
  if (!current?.dates.length) return []
  const first = current.dates[0]!
  const last = current.dates[current.dates.length - 1]!
  return market.activeEvents.filter((event) => event.publ_date >= first && event.publ_date <= last)
})
const activeMeta = computed(() => market.stocks.find((item) => item.code === market.activeCode))

async function refreshStock(code: string) {
  if (!code) {
    stock.value = null
    return
  }
  stockLoading.value = true
  try {
    stock.value = await market.loadStock(code)
  } finally {
    stockLoading.value = false
  }
}

watch(() => market.activeCode, refreshStock)
onMounted(async () => {
  await market.initialize()
  await refreshStock(market.activeCode)
})
</script>

<template>
  <section>
    <header class="view-header explorer-heading">
      <div>
        <h1>业绩预告事件研究</h1>
        <p>披露日标记在 K 线上，任何交易语义从下一交易日开始。</p>
      </div>
      <div v-if="market.manifest" class="dataset-meta">
        <Database :size="15" />
        <span>{{ market.manifest.date_range[0] }} — {{ market.manifest.date_range[1] }}</span>
      </div>
    </header>

    <div v-if="market.error" class="state-message error-state">{{ market.error }}</div>
    <div v-else-if="market.loading" class="state-message"><LoaderCircle class="spin" :size="20" /> 正在读取本地数据</div>
    <template v-else>
      <StockPicker
        :stocks="market.stocks"
        :active-code="market.activeCode"
        @select="market.selectStock"
      />

      <div class="research-toolbar">
        <div class="active-stock-meta">
          <strong>{{ activeMeta?.name ?? '—' }}</strong>
          <span>{{ activeMeta?.code }} · {{ activeMeta?.industry }}</span>
        </div>
        <div class="range-control" aria-label="K 线时间区间">
          <button
            v-for="item in ranges"
            :key="item.value"
            type="button"
            :class="{ active: market.explorerRange === item.value }"
            @click="market.explorerRange = item.value"
          >
            {{ item.label }}
          </button>
        </div>
        <div class="event-count"><CalendarClock :size="15" /> {{ visibleEvents.length }} 个预告点</div>
      </div>

      <div v-if="stockLoading" class="state-message chart-loading"><LoaderCircle class="spin" :size="20" /></div>
      <div v-else class="explorer-grid">
        <KLineChart :stock="visibleStock" :events="visibleEvents" />
        <ReturnStats :stock="visibleStock" />
      </div>

      <p class="pit-note">
        图中金色标记定位于 <strong>publ_date</strong>；“若当时买入”等计算须从
        <strong>usable_from</strong> 起算。价格为构建期复权结果。
      </p>
    </template>
  </section>
</template>
