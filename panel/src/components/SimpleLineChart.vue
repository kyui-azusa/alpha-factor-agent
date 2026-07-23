<script setup lang="ts">
import { computed } from 'vue'

interface Point {
  date: string
  value: number
}

interface LineSeries {
  label: string
  color: string
  points: Point[]
}

const props = withDefaults(
  defineProps<{
    series: LineSeries[]
    valueFormat?: 'number' | 'percent'
    zeroLine?: boolean
  }>(),
  { valueFormat: 'number', zeroLine: false },
)

const width = 960
const height = 320
const inset = { top: 20, right: 22, bottom: 35, left: 58 }

const values = computed(() => props.series.flatMap((item) => item.points.map((point) => point.value)))
const domain = computed(() => {
  const source = values.value.length ? values.value : [0, 1]
  let min = Math.min(...source)
  let max = Math.max(...source)
  if (props.zeroLine) {
    min = Math.min(min, 0)
    max = Math.max(max, 0)
  }
  const padding = Math.max((max - min) * 0.1, 0.001)
  return { min: min - padding, max: max + padding }
})

function coordinates(points: Point[]): string {
  const innerWidth = width - inset.left - inset.right
  const innerHeight = height - inset.top - inset.bottom
  const span = domain.value.max - domain.value.min || 1
  return points
    .map((point, index) => {
      const x = inset.left + (index / Math.max(points.length - 1, 1)) * innerWidth
      const y = inset.top + ((domain.value.max - point.value) / span) * innerHeight
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

function yPosition(value: number): number {
  const innerHeight = height - inset.top - inset.bottom
  return inset.top + ((domain.value.max - value) / (domain.value.max - domain.value.min || 1)) * innerHeight
}

function formatValue(value: number): string {
  return props.valueFormat === 'percent' ? `${(value * 100).toFixed(1)}%` : value.toFixed(2)
}

const ticks = computed(() =>
  Array.from({ length: 5 }, (_, index) => domain.value.min + ((domain.value.max - domain.value.min) * index) / 4),
)
const firstDate = computed(() => props.series.find((item) => item.points.length)?.points[0]?.date ?? '')
const lastDate = computed(() => {
  const points = props.series.find((item) => item.points.length)?.points ?? []
  return points[points.length - 1]?.date ?? ''
})
</script>

<template>
  <div class="simple-chart">
    <div class="chart-legend">
      <span v-for="item in series" :key="item.label"><i :style="{ background: item.color }"></i>{{ item.label }}</span>
    </div>
    <svg :viewBox="`0 0 ${width} ${height}`" role="img" aria-label="时序折线图">
      <g v-for="tick in ticks" :key="tick">
        <line :x1="inset.left" :x2="width - inset.right" :y1="yPosition(tick)" :y2="yPosition(tick)" class="chart-grid" />
        <text :x="inset.left - 10" :y="yPosition(tick) + 4" text-anchor="end">{{ formatValue(tick) }}</text>
      </g>
      <line
        v-if="zeroLine && domain.min < 0 && domain.max > 0"
        :x1="inset.left"
        :x2="width - inset.right"
        :y1="yPosition(0)"
        :y2="yPosition(0)"
        class="zero-line"
      />
      <polyline
        v-for="item in series"
        :key="item.label"
        :points="coordinates(item.points)"
        :stroke="item.color"
        class="chart-line"
      />
      <text :x="inset.left" :y="height - 10">{{ firstDate }}</text>
      <text :x="width - inset.right" :y="height - 10" text-anchor="end">{{ lastDate }}</text>
    </svg>
  </div>
</template>
