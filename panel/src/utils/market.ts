import type { ChartRange, StockData } from '@/types/market'

export const RANGE_BARS: Record<ChartRange, number> = {
  '1m': 22,
  '3m': 66,
  '1y': 250,
  all: Number.POSITIVE_INFINITY,
}

export function sliceStock(stock: StockData, range: ChartRange): StockData {
  const count = RANGE_BARS[range]
  if (!Number.isFinite(count) || stock.dates.length <= count) return stock
  const start = stock.dates.length - count
  return {
    ...stock,
    dates: stock.dates.slice(start),
    ohlc: stock.ohlc.slice(start),
    volume: stock.volume.slice(start),
    ret: stock.ret.slice(start),
  }
}

export interface ReturnSummary {
  totalReturn: number | null
  annualVolatility: number | null
  maxDrawdown: number | null
  observations: number
}

export function calculateReturnSummary(stock: StockData | null): ReturnSummary {
  if (!stock || stock.ohlc.length < 2) {
    return { totalReturn: null, annualVolatility: null, maxDrawdown: null, observations: 0 }
  }
  const closes = stock.ohlc.map((item) => item[3])
  const firstClose = closes[0]
  const lastClose = closes[closes.length - 1]
  if (firstClose === undefined || lastClose === undefined) {
    return { totalReturn: null, annualVolatility: null, maxDrawdown: null, observations: 0 }
  }
  const returns = stock.ret.filter((value): value is number => value !== null && Number.isFinite(value))
  const mean = returns.reduce((sum, value) => sum + value, 0) / Math.max(returns.length, 1)
  const variance =
    returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(returns.length - 1, 1)
  let peak = firstClose
  let maxDrawdown = 0
  for (const close of closes) {
    peak = Math.max(peak, close)
    maxDrawdown = Math.min(maxDrawdown, close / peak - 1)
  }
  return {
    totalReturn: lastClose / firstClose - 1,
    annualVolatility: Math.sqrt(variance * 252),
    maxDrawdown,
    observations: closes.length,
  }
}

export function dateTimestamp(date: string): number {
  return new Date(`${date}T00:00:00+08:00`).getTime()
}
