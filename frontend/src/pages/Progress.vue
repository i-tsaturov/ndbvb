<template>
  <div class="page">
    <div class="page-head">
      <h1>Tasks</h1>
      <span class="sub">submit the flag you found, the task is verified on the server</span>
    </div>

    <div class="grid" style="grid-template-columns: 1fr 340px; align-items: start;">
      <div class="stack" style="gap:18px">
        <div class="card">
          <div class="card-title">Challenges</div>
          <div v-if="st.total" class="progress-wrap">
            <div class="progress-track">
              <div class="progress-fill" :style="{ width: (st.solved_count / st.total) * 100 + '%' }"></div>
            </div>
            <div class="row spread mono" style="font-size:12px">
              <span>{{ st.solved_count }} of {{ st.total }} found</span>
              <span class="muted">{{ st.remaining }} remaining</span>
              <span>{{ st.points }} / {{ st.points_total }} pts</span>
            </div>
          </div>
          <label class="row" style="margin:10px 0 6px; cursor:pointer; font-size:13px">
            <input type="checkbox" v-model="showDetails" />
            Show details (titles, categories, hints)
          </label>
          <table class="data">
            <tbody>
              <tr v-if="!list.length"><td><div class="skeleton" style="height:18px"></div></td></tr>
              <tr v-for="(c, i) in list" :key="c.code" :class="{ done: c.solved }">
                <td style="width:34px" class="mono">{{ c.solved ? '✓' : '○' }}</td>
                <td>
                  <div :class="{ strike: c.solved && showDetails }">
                    {{ showDetails ? c.title : 'Task ' + String(i + 1).padStart(2, '0') }}
                  </div>
                  <div v-if="showDetails && !c.solved && c.hint" class="hint-line muted">{{ c.hint }}</div>
                </td>
                <td><span v-if="showDetails" class="chip">{{ c.category }}</span></td>
                <td class="mono r muted">{{ c.points }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="stack" style="gap:18px">
        <div class="card">
          <div class="card-title">Submit a flag</div>
          <div class="field">
            <label>Nickname</label>
            <input class="input" v-model="nickname" placeholder="your nick" @change="saveNick" />
            <span class="hint">saved in this browser</span>
          </div>
          <div class="field">
            <label>Flag</label>
            <input class="input mono" v-model="flag" placeholder="FLAG{…}" @keyup.enter="submit" />
          </div>
          <button class="btn red" style="width:100%" :disabled="busy || !nickname.trim()" @click="submit">
            {{ busy ? 'Checking…' : 'Submit' }}
          </button>
          <p v-if="result" class="mono result" :class="{ ok: result.status === 'solved' || result.status === 'already solved' }">
            {{ result.status === 'solved' ? `solved: ${result.challenge} (+${result.points})`
               : result.status === 'already solved' ? `already solved: ${result.challenge}`
               : `error: ${result.detail || result.error}` }}
          </p>
        </div>

        <div class="card">
          <div class="card-title">How it counts</div>
          <p class="muted" style="font-size:13px">
            Every accepted flag is stored in the database for your nickname, so your
            progress survives page reloads and stand restarts. Full walkthroughs live in
            docs/SOLUTIONS.md; hints here are spoiler-level one-liners.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const NICK_KEY = 'ob_nickname'

const nickname = ref(localStorage.getItem(NICK_KEY) || '')
const flag = ref('')
const busy = ref(false)
const result = ref<any>(null)
const showDetails = ref(false)
const list = ref<any[]>([])
const st = ref<any>({ solved_count: 0, total: 0, remaining: 0, points: 0, points_total: 0 })

function saveNick() {
  if (nickname.value.trim()) localStorage.setItem(NICK_KEY, nickname.value.trim())
}

async function refresh() {
  const nick = encodeURIComponent(nickname.value.trim())
  list.value = await api(`/api/v1/progress/challenges${nick ? `?nickname=${nick}` : ''}`)
  st.value = await api(`/api/v1/progress/state?nickname=${nick}`)
}

async function submit() {
  if (!nickname.value.trim() || !flag.value.trim()) return
  busy.value = true
  result.value = null
  try {
    result.value = await api('/api/v1/progress/submit', {
      method: 'POST',
      body: JSON.stringify({ nickname: nickname.value.trim(), flag: flag.value.trim() }),
    })
    flag.value = ''
    saveNick()
    await refresh()
  } catch (e: any) {
    result.value = { status: 'error', detail: e.message }
  } finally {
    busy.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.progress-wrap { margin-bottom: 6px; }
.progress-track {
  height: 8px; border-radius: 999px; background: var(--bg);
  border: 1px solid var(--line); overflow: hidden; margin-bottom: 8px;
}
.progress-fill { height: 100%; background: var(--red); transition: width 0.4s ease; }
tr.done td { opacity: 0.62; }
.strike { text-decoration: line-through; }
.hint-line { font-size: 12px; margin-top: 4px; }
.result { margin-top: 12px; font-size: 13px; color: var(--red); }
.result.ok { color: #1E7A2E; }
.r { text-align: right; }
</style>
