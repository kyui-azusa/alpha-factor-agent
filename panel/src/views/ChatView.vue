<script setup lang="ts">
import {
  ArrowRight,
  Bot,
  ChevronRight,
  Globe2,
  LoaderCircle,
  Wrench,
} from '@lucide/vue'
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useMarketStore } from '@/stores/market'
import { usePortfolioStore } from '@/stores/portfolio'
import { DEFAULT_FACTOR_CLUE } from '@/research/workbench'

interface AgentReply {
  title: string
  body: string
  tool: string
  route: string
  routeLabel: string
}

const router = useRouter()
const market = useMarketStore()
const portfolio = usePortfolioStore()
const prompt = ref('')
const webEnabled = ref(false)
const submittedPrompt = ref('')
const busy = ref(false)
const reply = ref<AgentReply | null>(null)
const conversation = ref<HTMLElement | null>(null)
let replyTimer: number | undefined

const examplePrompt = DEFAULT_FACTOR_CLUE

onMounted(() => market.initialize())
onBeforeUnmount(() => window.clearTimeout(replyTimer))

function resolveReply(text: string): AgentReply {
  if (text.includes('组合') || text.includes('等权')) {
    portfolio.setCodes(['000651.SZ', '000858.SZ', '600519.SH'])
    portfolio.mode = 'equal'
    return {
      title: '三只龙头等权组合已准备好',
      body: '组合收益将由浏览器对本地复权收益序列逐日加权，不经过模型计算。',
      tool: '组合构建',
      route: '/portfolio',
      routeLabel: '查看组合',
    }
  }
  if (/生成|构造|线索|语气|文本/.test(text) && /因子|Alpha|alpha/.test(text)) {
    return {
      title: '研究线索已整理为任务合同草稿',
      body: '我会先展示经济现象、可观测代理、A 股映射和能力预检；缺少字段或 PIT 证明的候选将被阻断并保留原因。',
      tool: '研究合同与候选池',
      route: `/workbench?clue=${encodeURIComponent(text)}`,
      routeLabel: '审阅生成工作台',
    }
  }
  if (text.includes('因子') || text.includes('动量')) {
    return {
      title: '动量基线结果已定位',
      body: '这是样本外预计算结果；公开视图只展示类别与图表，不披露表达式和调优参数。',
      tool: '因子结果',
      route: '/factors?factor=baseline_momentum_20d',
      routeLabel: '查看结果',
    }
  }
  market.showStocks(['000651.SZ'], '1y')
  return {
    title: '格力电器近一年事件视图已准备好',
    body: '金色标记对应公告披露日，任何交易语义仍从下一个交易日开始。',
    tool: '公告事件研究',
    route: '/research',
    routeLabel: '打开图表',
  }
}

async function submit(text = prompt.value) {
  const value = text.trim()
  if (!value || busy.value) return
  submittedPrompt.value = value
  prompt.value = ''
  reply.value = null
  busy.value = true
  await nextTick()
  conversation.value?.scrollIntoView({ behavior: 'smooth' })
  replyTimer = window.setTimeout(() => {
    reply.value = resolveReply(value)
    busy.value = false
    nextTick(() => conversation.value?.scrollIntoView({ behavior: 'smooth', block: 'end' }))
  }, 650)
}

function resetConversation() {
  window.clearTimeout(replyTimer)
  submittedPrompt.value = ''
  reply.value = null
  busy.value = false
}
</script>

<template>
  <section class="chat-home" :class="{ 'has-conversation': submittedPrompt }">
    <div v-if="!submittedPrompt" class="chat-welcome">
      <div class="agent-symbol"><Bot :size="22" /></div>
      <h1>今天想研究什么？</h1>
      <p>描述问题，我会调用确定性研究工具。</p>
    </div>

    <div v-else ref="conversation" class="conversation-stream" aria-live="polite">
      <div class="user-message">{{ submittedPrompt }}</div>
      <div v-if="busy" class="assistant-thinking">
        <LoaderCircle class="spin" :size="17" />
        <span>正在选择研究技能</span>
      </div>
      <article v-else-if="reply" class="assistant-message">
        <div class="assistant-avatar"><Bot :size="16" /></div>
        <div>
          <div class="tool-call"><Wrench :size="13" /> 已调用 {{ reply.tool }}</div>
          <h2>{{ reply.title }}</h2>
          <p>{{ reply.body }}</p>
          <button type="button" class="result-link" @click="router.push(reply.route)">
            {{ reply.routeLabel }} <ChevronRight :size="15" />
          </button>
        </div>
      </article>
    </div>

    <div class="composer-area">
      <form class="chat-composer" @submit.prevent="submit()">
        <textarea
          v-model="prompt"
          rows="2"
          aria-label="给 Alpha Agent 分配任务"
          placeholder="分配一个研究任务或提出问题"
          @keydown.enter.exact.prevent="submit()"
        ></textarea>
        <div class="composer-toolbar">
          <div class="composer-tools">
            <button
              type="button"
              class="composer-tool"
              :class="{ active: webEnabled }"
              :aria-pressed="webEnabled"
              :title="webEnabled ? '关闭网页检索意图' : '表达网页检索意图'"
              @click="webEnabled = !webEnabled"
            >
              <Globe2 :size="15" /> 网页
            </button>
            <span v-if="webEnabled" class="web-intent-status" aria-live="polite">
              仅记录意图，当前不会联网
            </span>
          </div>
          <button type="submit" class="composer-send" :disabled="!prompt.trim() || busy" title="发送">
            <ArrowRight :size="18" />
          </button>
        </div>
      </form>

      <div v-if="!submittedPrompt" class="suggestion-row" aria-label="示例任务">
        <button type="button" @click="submit(examplePrompt)">
        <span>示例研究线索</span>{{ examplePrompt }}
        </button>
      </div>

      <button v-else type="button" class="new-thread-link" @click="resetConversation">清除对话</button>
      <p class="agent-disclaimer">Agent 负责理解与编排，数值始终由确定性代码生成。</p>
    </div>
  </section>
</template>
