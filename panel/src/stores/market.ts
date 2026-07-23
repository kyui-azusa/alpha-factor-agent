import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import type {
  BenchmarkData,
  ChartRange,
  FactorResult,
  ForecastEvent,
  Manifest,
  StockData,
} from '@/types/market'

const dataUrl = (path: string) => `${import.meta.env.BASE_URL}data/${path}`

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(dataUrl(path))
  if (!response.ok) throw new Error(`本地数据读取失败 (${response.status})`)
  return response.json() as Promise<T>
}

export const useMarketStore = defineStore('market', () => {
  const manifest = ref<Manifest | null>(null)
  const events = ref<ForecastEvent[]>([])
  const selectedCodes = ref<string[]>([])
  const activeCode = ref('')
  const explorerRange = ref<ChartRange>('1y')
  const loading = ref(false)
  const error = ref('')
  const stockCache = new Map<string, StockData>()
  const factorCache = new Map<string, FactorResult>()
  let benchmarkCache: BenchmarkData | null = null

  const stocks = computed(() => manifest.value?.stocks ?? [])
  const activeEvents = computed(() => events.value.filter((event) => event.code === activeCode.value))

  async function initialize() {
    if (manifest.value) return
    loading.value = true
    error.value = ''
    try {
      const [nextManifest, eventPayload] = await Promise.all([
        readJson<Manifest>('manifest.json'),
        readJson<{ events: ForecastEvent[] }>('events.json'),
      ])
      manifest.value = nextManifest
      events.value = eventPayload.events
      const first = nextManifest.stocks[0]?.code ?? ''
      selectedCodes.value = first ? [first] : []
      activeCode.value = first
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '本地数据读取失败'
    } finally {
      loading.value = false
    }
  }

  async function loadStock(code: string): Promise<StockData> {
    const cached = stockCache.get(code)
    if (cached) return cached
    const stock = await readJson<StockData>(`stocks/${code}.json`)
    stockCache.set(code, stock)
    return stock
  }

  async function loadBenchmark(): Promise<BenchmarkData> {
    if (benchmarkCache) return benchmarkCache
    benchmarkCache = await readJson<BenchmarkData>('benchmark.json')
    return benchmarkCache
  }

  async function loadFactor(id: string): Promise<FactorResult> {
    const cached = factorCache.get(id)
    if (cached) return cached
    const factor = await readJson<FactorResult>(`factors/${id}.json`)
    factorCache.set(id, factor)
    return factor
  }

  function selectStock(code: string) {
    if (!selectedCodes.value.includes(code)) selectedCodes.value.push(code)
    activeCode.value = code
  }

  function removeStock(code: string) {
    selectedCodes.value = selectedCodes.value.filter((item) => item !== code)
    if (activeCode.value === code) activeCode.value = selectedCodes.value[0] ?? ''
  }

  function showStocks(codes: string[], range: ChartRange = '1y') {
    const available = new Set(stocks.value.map((stock) => stock.code))
    const valid = [...new Set(codes)].filter((code) => available.has(code))
    if (!valid.length) return
    selectedCodes.value = valid
    activeCode.value = valid[0]!
    explorerRange.value = range
  }

  return {
    manifest,
    events,
    stocks,
    selectedCodes,
    activeCode,
    explorerRange,
    activeEvents,
    loading,
    error,
    initialize,
    loadStock,
    loadBenchmark,
    loadFactor,
    selectStock,
    removeStock,
    showStocks,
  }
})
