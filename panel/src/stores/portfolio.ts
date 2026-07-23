import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type WeightMode = 'equal' | 'custom'

export const usePortfolioStore = defineStore('portfolio', () => {
  const codes = ref<string[]>([])
  const mode = ref<WeightMode>('equal')
  const rawWeights = ref<Record<string, number>>({})

  const normalizedWeights = computed<Record<string, number>>(() => {
    if (!codes.value.length) return {}
    if (mode.value === 'equal') {
      const weight = 1 / codes.value.length
      return Object.fromEntries(codes.value.map((code) => [code, weight]))
    }
    const values = codes.value.map((code) => Math.max(0, rawWeights.value[code] ?? 0))
    const total = values.reduce((sum, value) => sum + value, 0)
    if (total <= 0) {
      const weight = 1 / codes.value.length
      return Object.fromEntries(codes.value.map((code) => [code, weight]))
    }
    return Object.fromEntries(codes.value.map((code, index) => [code, values[index]! / total]))
  })

  function setCodes(nextCodes: string[]) {
    codes.value = [...new Set(nextCodes)]
    for (const code of codes.value) {
      if (rawWeights.value[code] === undefined) rawWeights.value[code] = 1
    }
  }

  function addCode(code: string) {
    if (codes.value.includes(code)) return
    codes.value.push(code)
    rawWeights.value[code] = 1
  }

  function removeCode(code: string) {
    codes.value = codes.value.filter((item) => item !== code)
    delete rawWeights.value[code]
  }

  function setWeight(code: string, value: number) {
    rawWeights.value[code] = Number.isFinite(value) ? Math.max(0, value) : 0
  }

  return {
    codes,
    mode,
    rawWeights,
    normalizedWeights,
    setCodes,
    addCode,
    removeCode,
    setWeight,
  }
})
