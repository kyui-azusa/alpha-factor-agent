<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, Search } from '@lucide/vue'

import type { StockMeta } from '@/types/market'

const props = defineProps<{
  stocks: StockMeta[]
  activeCode: string
}>()

const emit = defineEmits<{
  select: [code: string]
}>()

const query = ref('')
const open = ref(false)

const normalized = computed(() => query.value.trim().toLowerCase())
const results = computed(() => {
  const term = normalized.value
  const matches = term
    ? props.stocks.filter(
        (stock) =>
          stock.code.toLowerCase().includes(term) || stock.name.toLowerCase().includes(term),
      )
    : props.stocks
  return matches.slice(0, 8)
})
const activeStock = computed(() => props.stocks.find((stock) => stock.code === props.activeCode))
const placeholder = computed(() => {
  const stock = activeStock.value
  return stock ? `${stock.name} · ${stock.code}` : '搜索股票代码或名称'
})

function choose(code: string) {
  emit('select', code)
  query.value = ''
  open.value = false
}
</script>

<template>
  <div class="stock-picker">
    <div class="search-wrap">
      <Search :size="17" />
      <input
        v-model="query"
        type="search"
        :placeholder="placeholder"
        aria-label="搜索股票代码或名称"
        @focus="open = true"
        @keydown.escape="open = false"
        @keydown.enter.prevent="results[0] && choose(results[0].code)"
      />
      <div v-if="open" class="search-results">
        <button v-for="stock in results" :key="stock.code" type="button" @click="choose(stock.code)">
          <span><strong>{{ stock.name }}</strong><small>{{ stock.code }} · {{ stock.industry }}</small></span>
          <Check v-if="stock.code === activeCode" :size="16" />
        </button>
        <p v-if="results.length === 0">未找到匹配股票</p>
      </div>
    </div>
  </div>
</template>
