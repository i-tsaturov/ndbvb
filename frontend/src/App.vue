<template>
  <div class="shell" :class="{ collapsed: !expanded }">
    <aside class="sidebar" :data-collapsed="(!expanded).toString()">
      <div class="sb-head">
        <router-link to="/" class="brand">
          <span class="mark"></span>
          <span v-if="expanded" class="name">OnlineBank</span>
        </router-link>
        <button class="btn ghost sm burger" aria-label="Menu" v-if="narrow" @click="expanded = !expanded">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
        </button>
      </div>
      <nav class="sb-nav" v-if="expanded || !narrow">
        <router-link to="/">Overview</router-link>
        <router-link to="/payments">Payments</router-link>
        <router-link to="/cards">Cards &amp; rewards</router-link>
        <router-link to="/accounts">Accounts</router-link>
        <router-link to="/exchange">Exchange</router-link>
        <router-link to="/statements">Statements</router-link>
        <router-link to="/profile">Profile</router-link>
        <router-link v-if="auth.isBackoffice" to="/backoffice">Back office</router-link>
        <router-link to="/tasks" class="score">Tasks</router-link>
      </nav>
      <div class="sb-tools" v-if="expanded || !narrow">
        <button class="bell" aria-label="Notifications" @click="toggleBell">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
            <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
          </svg>
          <span v-if="unread" class="badge">{{ unread }}</span>
        </button>
      </div>
      <div class="sidebar-user sb-foot" v-if="expanded || !narrow">
        <template v-if="auth.authenticated">
          <div class="who">{{ firstName }}</div>
          <button class="btn ghost sm" @click="logout">Log out</button>
        </template>
        <router-link v-else to="/login" class="btn sm">Log in</router-link>
      </div>
      <div class="bell-drop card" v-if="bellOpen">
        <div class="card-title" style="margin:0 0 8px">Notifications</div>
        <div v-if="!notifications.length" class="muted" style="font-size:13px">Nothing yet</div>
        <div v-for="(n, i) in notifications" :key="i" class="bell-item">
          <div class="muted mono" style="font-size:11px">{{ (n.ts || '').replace('T', ' ').slice(5, 16) }}</div>
          <div style="font-size:13px">{{ n.text }}</div>
        </div>
      </div>
    </aside>
    <main class="content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from './stores/auth'
import { api } from './api'

const auth = useAuth()
const router = useRouter()
const narrow = ref(window.innerWidth < 900)
const bellOpen = ref(false)
const notifications = ref<any[]>([])
const unread = ref(0)
const firstName = computed(() => {
  const u: any = auth.user
  return u?.first_name || u?.firstName || 'Customer'
})

async function loadBell() {
  if (!auth.authenticated) return
  try {
    notifications.value = await api('/api/v1/notifications')
    unread.value = notifications.value.filter((n: any) => !n.read).length
  } catch { notifications.value = [] }
}

async function toggleBell() {
  bellOpen.value = !bellOpen.value
  if (!bellOpen.value) return
  await loadBell()
  try {
    await api('/api/v1/notifications/read', { method: 'POST', body: '{}' })
    unread.value = 0
  } catch { }
}

function onDocClick(e: MouseEvent) {
  if (!bellOpen.value) return
  const target = e.target as HTMLElement
  if (target.closest('.bell') || target.closest('.bell-drop')) return
  bellOpen.value = false
}
const expanded = ref(!narrow.value)

function onResize() {
  narrow.value = window.innerWidth < 900
  if (!narrow.value) expanded.value = true
}

watch(() => auth.authenticated, (now) => {
  if (now) loadBell()
  else { notifications.value = []; unread.value = 0; bellOpen.value = false }
})

onMounted(async () => {
  window.addEventListener('resize', onResize)
  document.addEventListener('click', onDocClick)
  if (auth.authenticated) {
    loadBell()
    if (!auth.user) {
      try {
        const p = await api('/api/v1/profile')
        auth.user = { login: p.login, first_name: p.first_name, is_backoffice: p.is_backoffice, role: p.role }
      } catch {
      }
    }
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  document.removeEventListener('click', onDocClick)
})

async function logout() {
  await auth.logout()
  await router.push('/login')
}
</script>

<style scoped>
.shell { display: flex; min-height: 100vh; }
.sidebar {
  width: 224px; flex-shrink: 0; display: flex; flex-direction: column;
  background: rgba(255, 255, 255, 0.92); backdrop-filter: blur(8px);
  border-right: 1px solid var(--line);
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
  transition: width 0.2s ease; z-index: 30;
}
.shell.collapsed .sidebar { width: 64px; }
.sb-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 14px 10px;
}
.brand { display: flex; align-items: center; gap: 8px; text-decoration: none; }
.mark { width: 22px; height: 6px; background: var(--red); border-radius: 1px; flex-shrink: 0; }
.name { font-weight: 700; font-size: 16px; letter-spacing: -0.01em; white-space: nowrap; }
.burger { font-size: 16px; line-height: 1; }
.sb-nav { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; flex: 1; }
.sb-nav a {
  display: flex; align-items: center; gap: 10px;
  text-decoration: none; font-size: 14px; color: var(--muted);
  padding: 9px 10px; border-radius: 8px; white-space: nowrap;
  transition: color 0.15s ease, background 0.15s ease;
}
.sb-nav a:hover { color: var(--ink); background: var(--bg); }
.sb-nav a.router-link-active { color: var(--ink); font-weight: 600; background: var(--bg); }
.sb-nav a.score { color: var(--red); }
.sb-foot {
  padding: 12px 14px; border-top: 1px solid var(--line);
  display: flex; flex-direction: column; gap: 8px; align-items: flex-start;
}
.sb-tools { padding: 0 14px 6px; }
.bell {
  position: relative; border: 1px solid var(--line); background: var(--card);
  border-radius: 10px; padding: 7px 10px; cursor: pointer;
  display: inline-flex; align-items: center; color: var(--ink);
}
.bell:hover { border-color: var(--ink); }
.bell .badge {
  position: absolute; top: -6px; right: -6px; background: var(--red); color: #fff;
  border-radius: 999px; font-size: 10px; padding: 1px 5px; font-family: var(--mono);
}
.bell-drop {
  position: fixed; left: 232px; bottom: 24px; width: 360px; max-width: 86vw;
  max-height: 420px; overflow-y: auto; z-index: 60;
}
.bell-item { border-top: 1px solid var(--line); padding: 8px 0; }
@media (max-width: 900px) { .bell-drop { left: 12px; bottom: 70px; } }
.who { font-size: 12px; word-break: break-all; }
.content { flex: 1; min-width: 0; }
@media (max-width: 900px) {
  .shell { flex-direction: column; }
  .sidebar {
    width: 100%; height: auto; position: static; flex-direction: row;
    align-items: center; overflow-x: auto; border-right: none;
    border-bottom: 1px solid var(--line);
  }
  .shell.collapsed .sidebar { width: 100%; }
  .sb-head { padding: 10px; width: 100%; }
  .sb-nav { flex-direction: row; padding: 0 8px 8px; }
  .sb-nav a span { display: none; }
  .sb-foot { border-top: none; border-left: 1px solid var(--line); margin-left: auto; }
}
</style>
