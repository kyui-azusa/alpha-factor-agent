<script setup lang="ts">
import {
  BarChart3,
  CandlestickChart,
  FlaskConical,
  Layers3,
  Menu,
  Moon,
  Plus,
  Sun,
  X,
} from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

type Theme = 'light' | 'dark'

const route = useRoute()
const sidebarOpen = ref(false)
const themeKey = 'alpha-theme'
const theme = ref<Theme>(document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')
const themeLabel = computed(() => (theme.value === 'light' ? '切换到深色' : '切换到浅色'))
const isChat = computed(() => route.name === 'chat')
const pageTitle = computed(() => {
  if (route.name === 'research') return '事件研究'
  if (route.name === 'portfolio') return '组合研究'
  if (route.name === 'factors') return '因子结果'
  return 'Alpha Agent'
})
const systemTheme = window.matchMedia('(prefers-color-scheme: light)')

function savedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(themeKey)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

function applyTheme(nextTheme: Theme) {
  theme.value = nextTheme
  document.documentElement.dataset.theme = nextTheme
}

function toggleTheme() {
  const nextTheme = theme.value === 'light' ? 'dark' : 'light'
  applyTheme(nextTheme)
  try {
    localStorage.setItem(themeKey, nextTheme)
  } catch {}
}

function followSystem(event: MediaQueryListEvent) {
  if (!savedTheme()) applyTheme(event.matches ? 'light' : 'dark')
}

function syncStoredTheme(event: StorageEvent) {
  if (event.key !== themeKey) return
  const nextTheme = event.newValue
  if (nextTheme === 'light' || nextTheme === 'dark') applyTheme(nextTheme)
  else applyTheme(systemTheme.matches ? 'light' : 'dark')
}

function closeSidebar() {
  sidebarOpen.value = false
}

onMounted(() => {
  systemTheme.addEventListener('change', followSystem)
  window.addEventListener('storage', syncStoredTheme)
})

onBeforeUnmount(() => {
  systemTheme.removeEventListener('change', followSystem)
  window.removeEventListener('storage', syncStoredTheme)
})
</script>

<template>
  <div class="agent-app">
    <Transition name="fade">
      <button
        v-if="sidebarOpen"
        type="button"
        class="sidebar-backdrop"
        aria-label="关闭导航"
        @click="closeSidebar"
      ></button>
    </Transition>

    <aside class="agent-sidebar" :class="{ open: sidebarOpen }">
      <header class="sidebar-brand">
        <RouterLink to="/" aria-label="Alpha Agent 首页" @click="closeSidebar">
          <span class="brand-mark"><FlaskConical :size="18" /></span>
          <span><strong>Alpha Agent</strong><small>RESEARCH</small></span>
        </RouterLink>
        <button type="button" class="sidebar-close" title="关闭导航" @click="closeSidebar">
          <X :size="18" />
        </button>
      </header>

      <RouterLink class="new-chat-button" to="/" @click="closeSidebar">
        <Plus :size="17" />
        <span>新对话</span>
      </RouterLink>

      <nav class="agent-nav" aria-label="研究工具">
        <span class="nav-label">研究工具</span>
        <RouterLink to="/research" @click="closeSidebar">
          <CandlestickChart :size="17" /><span>事件研究</span>
        </RouterLink>
        <RouterLink to="/portfolio" @click="closeSidebar">
          <Layers3 :size="17" /><span>组合研究</span>
        </RouterLink>
        <RouterLink to="/factors" @click="closeSidebar">
          <BarChart3 :size="17" /><span>因子结果</span>
        </RouterLink>
      </nav>

    </aside>

    <main class="agent-main">
      <header class="agent-topbar">
        <button type="button" class="topbar-menu" title="打开导航" @click="sidebarOpen = true">
          <Menu :size="18" />
        </button>
        <strong>{{ pageTitle }}</strong>
        <button
          type="button"
          class="theme-toggle"
          :aria-label="themeLabel"
          :title="themeLabel"
          :aria-pressed="theme === 'light'"
          @click="toggleTheme"
        >
          <Moon v-if="theme === 'light'" :size="17" />
          <Sun v-else :size="17" />
        </button>
      </header>

      <div class="route-surface" :class="{ 'chat-surface': isChat, 'research-surface': !isChat }">
        <RouterView />
      </div>
    </main>
  </div>
</template>
