<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Bot, ChevronDown, LoaderCircle, Send, Settings, Trash2, X } from '@lucide/vue'
import { useRouter } from 'vue-router'

import { useMarketStore } from '@/stores/market'
import { usePortfolioStore } from '@/stores/portfolio'
import type { ChartRange } from '@/types/market'

interface LLMSettings {
  baseUrl: string
  apiKey: string
  model: string
}

type ViewAction =
  | { action: 'show_stocks'; codes: string[]; range: ChartRange }
  | { action: 'show_factor'; id: string }
  | { action: 'build_portfolio'; codes: string[]; weights: 'equal' }

interface Preset {
  label: string
  action: ViewAction
  conclusion: string
}

const STORAGE_KEY = 'alpha-panel-llm'
const EMPTY_SETTINGS: LLMSettings = { baseUrl: '', apiKey: '', model: '' }
const market = useMarketStore()
const portfolio = usePortfolioStore()
const router = useRouter()
const settings = ref<LLMSettings>({ ...EMPTY_SETTINGS })
const draft = ref<LLMSettings>({ ...EMPTY_SETTINGS })
const showSettings = ref(false)
const expanded = ref(false)
const prompt = ref('')
const busy = ref(false)
const message = ref('选择一个离线预设，直接切换到对应研究视图。')
const error = ref('')

const configured = computed(() =>
  Boolean(settings.value.baseUrl && settings.value.apiKey && settings.value.model),
)
const presets: Preset[] = [
  {
    label: '格力预告与走势',
    action: { action: 'show_stocks', codes: ['000651.SZ'], range: '1y' },
    conclusion: '已定位格力电器近一年行情；金色标记是披露日，交易语义仍从下一交易日起算。',
  },
  {
    label: '三只龙头等权',
    action: {
      action: 'build_portfolio',
      codes: ['000651.SZ', '000858.SZ', '600519.SH'],
      weights: 'equal',
    },
    conclusion: '已构建三只股票的等权组合，收益由浏览器对本地复权收益序列逐日加权。',
  },
  {
    label: '动量基线结果',
    action: { action: 'show_factor', id: 'baseline_momentum_20d' },
    conclusion: '已打开动量类别的样本外预计算结果；公开面板不含表达式与调优参数。',
  },
]

onMounted(async () => {
  await market.initialize()
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) settings.value = JSON.parse(stored) as LLMSettings
  } catch {
    localStorage.removeItem(STORAGE_KEY)
  }
})

function openSettings() {
  draft.value = { ...settings.value }
  showSettings.value = true
}

function saveSettings() {
  settings.value = {
    baseUrl: draft.value.baseUrl.trim().replace(/\/$/, ''),
    apiKey: draft.value.apiKey.trim(),
    model: draft.value.model.trim(),
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings.value))
  showSettings.value = false
  error.value = ''
}

function clearSettings() {
  settings.value = { ...EMPTY_SETTINGS }
  draft.value = { ...EMPTY_SETTINGS }
  localStorage.removeItem(STORAGE_KEY)
  showSettings.value = false
  message.value = '模型配置已从本机浏览器清除，离线预设仍可使用。'
}

function validCodes(codes: unknown): codes is string[] {
  if (!Array.isArray(codes) || !codes.length || !codes.every((code) => typeof code === 'string')) {
    return false
  }
  const available = new Set(market.stocks.map((stock) => stock.code))
  return codes.every((code) => available.has(code))
}

function parseAction(content: string): ViewAction | null {
  try {
    const cleaned = content.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')
    const value = JSON.parse(cleaned) as Record<string, unknown>
    if (value.action === 'show_stocks' && validCodes(value.codes)) {
      const range = value.range
      if (range === '1m' || range === '3m' || range === '1y' || range === 'all') {
        return { action: value.action, codes: value.codes, range }
      }
    }
    if (
      value.action === 'show_factor' &&
      typeof value.id === 'string' &&
      market.manifest?.factors.some((factor) => factor.id === value.id)
    ) {
      return { action: value.action, id: value.id }
    }
    if (value.action === 'build_portfolio' && validCodes(value.codes) && value.weights === 'equal') {
      return { action: value.action, codes: value.codes, weights: value.weights }
    }
  } catch {
    return null
  }
  return null
}

async function applyAction(action: ViewAction, conclusion?: string) {
  if (action.action === 'show_stocks') {
    market.showStocks(action.codes, action.range)
    await router.push('/research')
    message.value = conclusion ?? `已打开 ${action.codes.join('、')} 的本地行情与事件标记。`
  } else if (action.action === 'show_factor') {
    await router.push({ path: '/factors', query: { factor: action.id } })
    message.value = conclusion ?? '已打开对应因子的公开预计算结果。'
  } else {
    portfolio.setCodes(action.codes)
    portfolio.mode = 'equal'
    await router.push('/portfolio')
    message.value = conclusion ?? '已用本地收益序列构建等权组合。'
  }
  error.value = ''
}

function endpoint(baseUrl: string): string {
  return baseUrl.endsWith('/chat/completions') ? baseUrl : `${baseUrl}/chat/completions`
}

function maskError(value: string): string {
  const key = settings.value.apiKey
  if (!key) return value
  return value.split(key).join(`***${key.slice(-4)}`)
}

async function submit() {
  if (!configured.value || !prompt.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const response = await fetch(endpoint(settings.value.baseUrl), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${settings.value.apiKey}`,
      },
      body: JSON.stringify({
        model: settings.value.model,
        temperature: 0,
        max_tokens: 180,
        response_format: { type: 'json_object' },
        messages: [
          {
            role: 'system',
            content:
              'Translate the request into exactly one JSON view action. Allowed schemas: {"action":"show_stocks","codes":["code"],"range":"1m|3m|1y|all"}, {"action":"show_factor","id":"public id"}, {"action":"build_portfolio","codes":["code"],"weights":"equal"}. Never calculate or return research numbers. Available codes: ' +
              market.stocks.map((stock) => stock.code).join(',') +
              '. Public factor ids: ' +
              (market.manifest?.factors.map((factor) => factor.id).join(',') ?? ''),
          },
          { role: 'user', content: prompt.value.trim() },
        ],
      }),
    })
    if (!response.ok) {
      const detail = maskError((await response.text()).slice(0, 300))
      throw new Error(`模型服务返回 ${response.status}${detail ? `：${detail}` : ''}`)
    }
    const payload = (await response.json()) as {
      choices?: Array<{ message?: { content?: string } }>
    }
    const action = parseAction(payload.choices?.[0]?.message?.content ?? '')
    if (!action) throw new Error('模型没有返回可验证的视图动作，请换一种说法。')
    await applyAction(action)
    prompt.value = ''
  } catch (cause) {
    if (cause instanceof TypeError) {
      error.value =
        '目标地址未允许浏览器跨域访问，请检查服务端 CORS：one-api/new-api 开启跨域；vLLM 配置 --allowed-origins；Ollama 设置 OLLAMA_ORIGINS。'
    } else {
      error.value = maskError(cause instanceof Error ? cause.message : '模型请求失败')
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="agent-console" aria-label="研究视图助手">
    <header>
      <button
        type="button"
        class="agent-toggle"
        :aria-expanded="expanded"
        aria-controls="agent-console-body"
        @click="expanded = !expanded"
      >
        <Bot :size="17" />
        <strong>研究助手</strong>
        <span>{{ expanded ? '收起助手' : '打开助手' }}</span>
        <ChevronDown :size="16" />
      </button>
      <button
        v-if="expanded"
        type="button"
        class="icon-button agent-settings"
        title="模型设置"
        aria-label="模型设置"
        @click="openSettings"
      >
        <Settings :size="16" />
      </button>
    </header>
    <Transition name="agent-reveal">
      <div v-if="expanded" id="agent-console-body" class="agent-body">
        <div class="preset-row" aria-label="离线预设问题">
          <button v-for="preset in presets" :key="preset.label" type="button" @click="applyAction(preset.action, preset.conclusion)">
            {{ preset.label }}
          </button>
        </div>
        <div class="agent-input">
          <input
            v-model="prompt"
            type="text"
            :disabled="!configured || busy"
            :placeholder="configured ? '用自然语言切换研究视图' : '需先配置模型，自由输入才可用'"
            aria-label="研究视图指令"
            @keydown.enter="submit"
          />
          <button type="button" class="send-button" :disabled="!configured || !prompt.trim() || busy" title="发送" @click="submit">
            <LoaderCircle v-if="busy" class="spin" :size="16" /><Send v-else :size="16" />
          </button>
        </div>
        <p :class="{ 'agent-error': error }">{{ error || message }}</p>
      </div>
    </Transition>

    <div v-if="showSettings" class="modal-backdrop" @click.self="showSettings = false">
      <form class="settings-dialog" @submit.prevent="saveSettings">
        <header><div><strong>模型设置</strong><span>OpenAI-compatible</span></div><button type="button" class="icon-button" title="关闭" @click="showSettings = false"><X :size="17" /></button></header>
        <label>Base URL<input v-model="draft.baseUrl" type="url" placeholder="https://api.openai.com/v1" required /></label>
        <label>API Key<input v-model="draft.apiKey" type="password" autocomplete="off" placeholder="sk-..." required /></label>
        <label>Model<input v-model="draft.model" type="text" placeholder="gpt-4.1-mini" required /></label>
        <p>密钥以明文存于本机浏览器，只发送到你填写的地址；公用电脑请用完清除。</p>
        <footer>
          <button v-if="configured" type="button" class="clear-button" @click="clearSettings"><Trash2 :size="14" /> 清除配置</button>
          <button type="submit" class="save-button">保存</button>
        </footer>
      </form>
    </div>
  </section>
</template>
