<script setup lang="ts">
import { computed, ref } from 'vue'
import { Plus, Search, Trash2 } from '@lucide/vue'

import type { StockMeta } from '@/types/market'
import type { WeightMode } from '@/stores/portfolio'

const props = defineProps<{
  stocks: StockMeta[]
  codes: string[]
  mode: WeightMode
  rawWeights: Record<string, number>
  normalizedWeights: Record<string, number>
}>()

const emit = defineEmits<{
  add: [code: string]
  remove: [code: string]
  'update:mode': [mode: WeightMode]
  weight: [code: string, value: number]
}>()

const query = ref('')
const results = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return []
  return props.stocks
    .filter(
      (stock) =>
        !props.codes.includes(stock.code) &&
        (stock.code.toLowerCase().includes(needle) || stock.name.toLowerCase().includes(needle)),
    )
    .slice(0, 6)
})
const selected = computed(() =>
  props.codes.map((code) => props.stocks.find((stock) => stock.code === code)).filter(Boolean) as StockMeta[],
)

function add(code: string) {
  emit('add', code)
  query.value = ''
}
</script>

<template>
  <aside class="portfolio-builder">
    <div class="builder-heading">
      <div>
        <strong>组合成分</strong>
        <small>{{ codes.length }} 只股票</small>
      </div>
      <div class="mode-control" aria-label="权重模式">
        <button type="button" :class="{ active: mode === 'equal' }" @click="emit('update:mode', 'equal')">等权</button>
        <button type="button" :class="{ active: mode === 'custom' }" @click="emit('update:mode', 'custom')">自定义</button>
      </div>
    </div>

    <div class="builder-search">
      <Search :size="15" />
      <input v-model="query" type="search" placeholder="添加股票" aria-label="搜索股票" />
      <div v-if="results.length" class="builder-results">
        <button v-for="stock in results" :key="stock.code" type="button" @click="add(stock.code)">
          <span><strong>{{ stock.name }}</strong><small>{{ stock.code }}</small></span>
          <Plus :size="15" />
        </button>
      </div>
    </div>

    <div class="weight-list">
      <div v-for="stock in selected" :key="stock.code" class="weight-row">
        <div>
          <strong>{{ stock.name }}</strong>
          <small>{{ stock.code }}</small>
        </div>
        <label>
          <span>归一化</span>
          <input
            v-if="mode === 'custom'"
            :value="rawWeights[stock.code]"
            type="number"
            min="0"
            step="0.1"
            :aria-label="`${stock.name} 原始权重`"
            @input="emit('weight', stock.code, Number(($event.target as HTMLInputElement).value))"
          />
          <b>{{ ((normalizedWeights[stock.code] ?? 0) * 100).toFixed(1) }}%</b>
        </label>
        <button type="button" class="icon-button" :title="`移除 ${stock.name}`" @click="emit('remove', stock.code)">
          <Trash2 :size="15" />
        </button>
      </div>
      <p v-if="!selected.length" class="empty-copy">搜索并添加至少一只股票。</p>
    </div>
  </aside>
</template>
