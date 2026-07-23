export interface StockMeta {
  code: string
  name: string
  industry: string
}

export interface FactorMeta {
  id: string
  label: string
  category: string
}

export interface Manifest {
  generated_at: string
  date_range: [string, string]
  stocks: StockMeta[]
  factors: FactorMeta[]
}

export interface StockData extends StockMeta {
  dates: string[]
  ohlc: [number, number, number, number][]
  volume: number[]
  ret: Array<number | null>
}

export interface ForecastEvent {
  code: string
  publ_date: string
  usable_from: string
  type: string
  growth_floor: number | null
  growth_ceiling: number | null
}

export interface SeriesPoint {
  date: string
  value: number
}

export interface BenchmarkData {
  label: string
  dates: string[]
  ret: number[]
  nav: number[]
}

export interface FactorResult extends FactorMeta {
  ic_series: SeriesPoint[]
  quantile_returns: Record<string, number>
  long_short_nav: SeriesPoint[]
  turnover: SeriesPoint[]
}

export type ChartRange = '1m' | '3m' | '1y' | 'all'
