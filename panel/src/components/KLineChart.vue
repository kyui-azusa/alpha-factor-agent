<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { dispose, init, type Chart, type Crosshair, type KLineData, type OverlayCreate } from 'klinecharts'

import type { ForecastEvent, StockData } from '@/types/market'
import { dateTimestamp } from '@/utils/market'

const props = defineProps<{
  stock: StockData | null
  events: ForecastEvent[]
}>()

const container = ref<HTMLElement | null>(null)
const hoveredEvent = ref<ForecastEvent | null>(null)
let chart: Chart | null = null
let overlayTimer: number | null = null
let themeObserver: MutationObserver | null = null

const eventByDate = computed(() => new Map(props.events.map((event) => [event.publ_date, event])))

function growthText(event: ForecastEvent) {
  if (event.growth_floor === null && event.growth_ceiling === null) return '幅度未披露'
  const floor = event.growth_floor === null ? '—' : `${event.growth_floor.toFixed(1)}%`
  const ceiling = event.growth_ceiling === null ? '—' : `${event.growth_ceiling.toFixed(1)}%`
  return floor === ceiling ? floor : `${floor} 至 ${ceiling}`
}

function themeColor(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function renderChart() {
  if (!container.value || !props.stock) return
  if (overlayTimer !== null) window.clearTimeout(overlayTimer)
  if (chart) dispose(chart)
  chart = init(container.value, {
    locale: 'zh-CN',
    timezone: 'Asia/Shanghai',
    styles: {
      grid: {
        horizontal: { color: themeColor('--chart-grid-horizontal'), size: 1 },
        vertical: { color: themeColor('--chart-grid-vertical'), size: 1 },
      },
      candle: {
        bar: {
          upColor: themeColor('--red'),
          downColor: themeColor('--green'),
          noChangeColor: themeColor('--muted'),
          upBorderColor: themeColor('--red'),
          downBorderColor: themeColor('--green'),
          noChangeBorderColor: themeColor('--muted'),
          upWickColor: themeColor('--red'),
          downWickColor: themeColor('--green'),
          noChangeWickColor: themeColor('--muted'),
        },
        tooltip: { showRule: 'follow_cross' },
      },
      xAxis: {
        axisLine: { color: themeColor('--chart-axis') },
        tickText: { color: themeColor('--muted') },
      },
      yAxis: {
        axisLine: { color: themeColor('--chart-axis') },
        tickText: { color: themeColor('--muted') },
      },
      crosshair: {
        horizontal: { line: { color: themeColor('--chart-crosshair') } },
        vertical: { line: { color: themeColor('--chart-crosshair') } },
      },
    },
  })
  if (!chart) return

  const rows: KLineData[] = props.stock.dates.map((date, index) => {
    const [open, high, low, close] = props.stock!.ohlc[index]!
    return {
      timestamp: dateTimestamp(date),
      open,
      high,
      low,
      close,
      volume: props.stock!.volume[index],
    }
  })
  chart.setDataLoader({
    getBars: ({ callback }) => callback(rows, false),
  })
  chart.setSymbol({ ticker: props.stock.code, pricePrecision: 2, volumePrecision: 0 })
  chart.setPeriod({ type: 'day', span: 1 })
  chart.createIndicator('VOL', false)
  chart.subscribeAction('onCrosshairChange', (data) => {
    const timestamp = (data as Crosshair | undefined)?.timestamp
    if (!timestamp) {
      hoveredEvent.value = null
      return
    }
    const date = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(timestamp)
    hoveredEvent.value = eventByDate.value.get(date) ?? null
  })

  overlayTimer = window.setTimeout(() => {
    overlayTimer = null
    if (!chart || !props.stock) return
    const highByDate = new Map(
      props.stock.dates.map((date, index) => [date, props.stock!.ohlc[index]![1]]),
    )
    for (const [date, event] of eventByDate.value) {
      const high = highByDate.get(date)
      if (high === undefined) continue
      const overlay: OverlayCreate<unknown> = {
        name: 'simpleAnnotation',
        groupId: 'forecast-events',
        lock: true,
        points: [{ timestamp: dateTimestamp(date), value: high }],
        extendData: event.type,
        styles: {
          line: { color: themeColor('--amber'), style: 'dashed', size: 1 },
          polygon: { color: themeColor('--amber'), borderColor: themeColor('--amber') },
          text: {
            color: themeColor('--marker-ink'),
            backgroundColor: themeColor('--amber'),
            borderColor: themeColor('--amber'),
            borderRadius: 3,
            paddingLeft: 5,
            paddingRight: 5,
            paddingTop: 2,
            paddingBottom: 2,
            size: 10,
          },
        },
      }
      chart.createOverlay(overlay)
    }
    chart.scrollToRealTime()
  }, 0)
}

watch(
  () => [props.stock, props.events] as const,
  () => nextTick(renderChart),
  { deep: false },
)

onMounted(() => {
  renderChart()
  themeObserver = new MutationObserver((mutations) => {
    if (mutations.some((mutation) => mutation.attributeName === 'data-theme')) {
      nextTick(renderChart)
    }
  })
  themeObserver.observe(document.documentElement, { attributes: true })
})
onBeforeUnmount(() => {
  if (overlayTimer !== null) window.clearTimeout(overlayTimer)
  themeObserver?.disconnect()
  if (chart) dispose(chart)
})
</script>

<template>
  <div class="chart-wrap">
    <div ref="container" class="kline-canvas"></div>
    <div v-if="hoveredEvent" class="event-tooltip">
      <strong>{{ hoveredEvent.type }}</strong>
      <span>{{ growthText(hoveredEvent) }}</span>
      <dl>
        <div><dt>披露标记</dt><dd>{{ hoveredEvent.publ_date }}</dd></div>
        <div><dt>交易可用</dt><dd>{{ hoveredEvent.usable_from }}</dd></div>
      </dl>
    </div>
  </div>
</template>
