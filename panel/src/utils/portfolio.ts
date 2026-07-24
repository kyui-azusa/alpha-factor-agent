import type { BenchmarkData, StockData } from '@/types/market'

export interface NavPoint {
  date: string
  value: number
}

export interface PortfolioResult {
  returns: number[]
  nav: NavPoint[]
  benchmark: NavPoint[]
  totalReturn: number | null
  annualVolatility: number | null
  maxDrawdown: number | null
  sharpe: number | null
}

const EMPTY_RESULT: PortfolioResult = {
  returns: [],
  nav: [],
  benchmark: [],
  totalReturn: null,
  annualVolatility: null,
  maxDrawdown: null,
  sharpe: null,
}

export function buildPortfolioResult(
  stocks: StockData[],
  weights: Record<string, number>,
  benchmark: BenchmarkData | null,
): PortfolioResult {
  if (!stocks.length) return EMPTY_RESULT

  const returnMaps = stocks.map(
    (stock) =>
      new Map(
        stock.dates.map((date, index) => [date, stock.ret[index]] as const),
      ),
  )
  const dates = stocks[0]!.dates.filter((date) =>
    returnMaps.every((values) => typeof values.get(date) === 'number'),
  )
  if (!dates.length) return EMPTY_RESULT

  const returns = dates.map((date) =>
    stocks.reduce(
      (sum, stock, index) => sum + (returnMaps[index]!.get(date) as number) * (weights[stock.code] ?? 0),
      0,
    ),
  )
  let navValue = 1
  const nav = dates.map((date, index) => {
    navValue *= 1 + returns[index]!
    return { date, value: navValue }
  })

  const benchmarkByDate = new Map(
    (benchmark?.dates ?? []).map((date, index) => [date, benchmark!.ret[index]!] as const),
  )
  let benchmarkValue = 1
  const benchmarkNav = dates
    .filter((date) => benchmarkByDate.has(date))
    .map((date) => {
      benchmarkValue *= 1 + benchmarkByDate.get(date)!
      return { date, value: benchmarkValue }
    })

  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length
  const variance =
    returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
    Math.max(returns.length - 1, 1)
  const annualVolatility = Math.sqrt(variance * 252)
  let peak = 1
  let maxDrawdown = 0
  for (const point of nav) {
    peak = Math.max(peak, point.value)
    maxDrawdown = Math.min(maxDrawdown, point.value / peak - 1)
  }

  return {
    returns,
    nav,
    benchmark: benchmarkNav,
    totalReturn: nav[nav.length - 1]!.value - 1,
    annualVolatility,
    maxDrawdown,
    sharpe: annualVolatility > 0 ? (mean * 252) / annualVolatility : null,
  }
}
