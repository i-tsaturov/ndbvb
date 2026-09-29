<template>
  <div class="page">
    <div class="page-head">
      <h1>Exchange</h1>
      <span class="sub">convert between your wallets</span>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <div class="card-title">Convert</div>
        <div class="field">
          <label>You give</label>
          <select class="select" v-model="from">
            <option v-for="a in accounts" :key="a.id" :value="a.id">
              {{ a.id }} · {{ fmt(a.balance) }} {{ a.currency }}
            </option>
          </select>
        </div>
        <div class="field">
          <label>You get</label>
          <div class="row">
            <select class="select" v-model="toCur">
              <option>USD</option><option>EUR</option><option>GHS</option>
            </select>
            <button class="btn sm ghost" @click="swap" title="Swap direction" style="display:inline-flex;align-items:center">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/></svg>
            </button>
          </div>
        </div>
        <div class="field">
          <label>Amount</label>
          <input class="input mono" v-model="amount" placeholder="100.00" />
        </div>
        <div class="rate-line mono" v-if="rate">
          1 {{ fromCur }} = {{ rate }} {{ toCur }}
        </div>
        <button class="btn red" :disabled="busy || !rate" @click="convert">
          {{ busy ? 'Converting…' : 'Convert now' }}
        </button>
      </div>

      <div class="card">
        <div class="card-title">{{ fromCur || 'USD' }} / {{ toCur }} rate</div>
        <Sparkline v-if="series.length" :rate="rateValue" :from="fromCur || 'USD'" :to="toCur" :series="series" />
        <p class="muted" style="font-size:12px;margin-top:10px">
          indicative intraday movement · quotes refresh with every conversion
        </p>
      </div>
    </div>
    <p v-if="error" class="err">{{ error }}</p>

    <div class="modal-backdrop" v-if="result" @click.self="result = null">
      <div class="card modal">
        <div class="card-title">Exchange completed</div>
        <p style="font-size:15px">
          Debited <b class="mono">{{ fmt(result.charged) }} {{ fromCur }}</b> from
          {{ accountLabel(from) }}
          → Credited <b class="mono">{{ fmt(result.credited) }} {{ toCur }}</b> to
          {{ walletLabel }}
        </p>
        <div class="new-balances">
          <div class="muted" style="font-size:12px;text-transform:uppercase;letter-spacing:.06em">New balances</div>
          <div class="mono big" style="margin-top:6px">{{ fmt(result.balance) }} {{ fromCur }}</div>
          <div class="mono big">{{ fmt(result.wallet_balance) }} {{ toCur }}</div>
        </div>
        <div class="row" style="margin-top:16px">
          <button class="btn red" @click="result = null">Close</button>
          <router-link class="btn ghost" to="/">View on dashboard</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import Sparkline from '../components/Sparkline.vue'

const accounts = ref<any[]>([])
const from = ref<number | null>(null)
const toCur = ref('GHS')
const amount = ref('')
const rate = ref<number | null>(null)
const series = ref<number[]>([])
const busy = ref(false)
const result = ref<any>(null)
const error = ref('')

const fromCur = computed(() => accounts.value.find((a: any) => a.id === from.value)?.currency || '')
const rateValue = computed(() => rate.value || 1)
const walletLabel = computed(() => {
  const a = accounts.value.find((x: any) => x.currency === toCur.value)
  return a ? `${a.name} (${a.id})` : 'your wallet'
})

function accountLabel(id: number | null) {
  const a = accounts.value.find((x: any) => x.id === (id ?? from.value))
  return a ? `${a.name} (${a.id})` : 'your account'
}

function fmt(v: number) {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)
}

function swap() {
  const target = accounts.value.find((a: any) => a.currency === toCur.value && a.id !== from.value)
    || accounts.value.find((a: any) => a.currency === toCur.value)
  const old = fromCur.value
  if (target) from.value = target.id
  if (old) toCur.value = old
}

async function loadRate() {
  if (!fromCur.value || fromCur.value === toCur.value) { rate.value = null; series.value = []; return }
  try {
    const res = await api(`/api/v1/exchange/rate?from_cur=${fromCur.value}&to_cur=${toCur.value}`)
    rate.value = res.rate
    const hist = await api(`/api/v1/exchange/rate/history?from_cur=${fromCur.value}&to_cur=${toCur.value}&points=48`)
    series.value = hist.map((p: any) => p.rate)
  } catch {
    rate.value = null
  }
}

async function convert() {
  busy.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await api('/api/v1/exchange/convert', {
      method: 'POST',
      body: JSON.stringify({ account_id: from.value, to_currency: toCur.value, amount: amount.value }),
    })
    accounts.value = await api('/api/v1/accounts')
  } catch (e: any) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  accounts.value = await api('/api/v1/accounts')
  from.value = accounts.value[0]?.id ?? null  // watchers load the rate
})

watch(fromCur, loadRate)
watch(toCur, loadRate)
</script>

<style scoped>
.err { color: var(--red); margin-top: 12px; }
.rate-line { font-size: 13px; color: var(--muted); margin-bottom: 14px; }
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(20, 22, 27, 0.45);
  display: flex; align-items: center; justify-content: center; z-index: 40;
}
.modal { width: 460px; max-width: 92vw; }
.new-balances { border-top: 1px solid var(--line); margin-top: 14px; padding-top: 12px; }
.big { font-size: 22px; font-weight: 600; margin-top: 2px; }
</style>
