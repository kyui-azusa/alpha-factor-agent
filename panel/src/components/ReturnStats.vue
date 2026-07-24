<script setup lang="ts">
import { computed } from 'vue'
import { Activity, CalendarDays, TrendingDown, TrendingUp } from '@lucide/vue'

import type { StockData } from '@/types/market'
import { calculateReturnSummary } from '@/utils/market'

const props = defineProps<{ stock: StockData | null }>()
const stats = computed(() => calculateReturnSummary(props.stock))

function percent(value: number | null) {
  return value === null ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}
</script>

<template>
  <aside class="stats-panel">
    <header>
      <span>区间统计</span>
      <small>{{ stats.observations }} 个交易日</small>
    </header>
    <dl>
      <div>
        <dt><TrendingUp :size="16" /> 区间涨跌</dt>
        <dd :class="{ positive: (stats.totalReturn ?? 0) >= 0, negative: (stats.totalReturn ?? 0) < 0 }">
          {{ percent(stats.totalReturn) }}
        </dd>
      </div>
      <div>
        <dt><Activity :size="16" /> 年化波动</dt>
        <dd>{{ percent(stats.annualVolatility) }}</dd>
      </div>
      <div>
        <dt><TrendingDown :size="16" /> 最大回撤</dt>
        <dd class="negative">{{ percent(stats.maxDrawdown) }}</dd>
      </div>
      <div>
        <dt><CalendarDays :size="16" /> 数据口径</dt>
        <dd class="text-value">复权日线</dd>
      </div>
    </dl>
  </aside>
</template>
