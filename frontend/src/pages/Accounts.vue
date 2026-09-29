<template>
  <div class="page">
    <div class="page-head">
      <h1>Accounts</h1>
      <span class="sub">your accounts, requisites and statements</span>
    </div>

    <div v-for="group in groups" :key="group.kind" style="margin-bottom: 22px">
      <div class="card-title">{{ group.label }}</div>
    <div class="grid cols-3">
      <div class="card hoverable account" v-for="a in group.items" :key="a.id">
        <div class="spread">
          <div class="card-title" style="margin:0">{{ a.kind }}</div>
          <span class="chip green">{{ a.status }}</span>
        </div>
        <div class="mono muted" style="font-size:13px">•• {{ String(a.number).slice(-4) }} · {{ a.currency }}</div>
        <div class="big-number" style="font-size:24px">{{ fmt(a.balance) }} <span class="cur">{{ a.currency }}</span></div>
        <div v-if="a.kind === 'savings'" class="kindline muted">APR {{ a.apr }}% · capitalized monthly</div>
        <div v-else-if="a.kind === 'goal'" class="kindline">
          <div class="progress-track"><div class="progress-fill" :style="{ width: Math.min(100, a.balance / (a.target_amount || 1) * 100) + '%' }"></div></div>
          <div class="muted" style="font-size:12px">{{ fmt(a.balance) }} of {{ fmt(a.target_amount || 0) }} {{ a.currency }}</div>
        </div>
        <div v-else-if="a.kind === 'credit'" class="kindline muted">Debt {{ fmt(a.debt) }} · limit {{ fmt(a.credit_limit) }} {{ a.currency }}</div>
        <div class="row" style="margin-top:12px; flex-wrap:wrap">
          <button class="btn sm ghost" @click="openRequisites(a)">Requisites</button>
          <button class="btn sm ghost" @click="openStatement(a)">Statement</button>
          <button class="btn sm ghost" @click="closeAccount(a)">Close account</button>
        </div>
      </div>
    </div>
    </div>

    <div class="card hoverable" style="display:flex;align-items:center;justify-content:center;min-height:150px;max-width:340px">
      <button class="btn ghost" @click="openNew = true">Open new account</button>
    </div>
    <p v-if="error" class="err">{{ error }}</p>

    <div class="modal-backdrop" v-if="openNew" @click.self="openNew = false">
      <div class="card dialog">
        <div class="card-title">Open a new account</div>
        <div class="field">
          <label>Currency</label>
          <select class="select" v-model="newCurrency">
            <option>USD</option><option>EUR</option><option>GHS</option>
          </select>
        </div>
        <div class="field">
          <label>Type</label>
          <select class="select" v-model="newKind">
            <option value="current">Current</option>
            <option value="savings">Savings</option>
            <option value="goal">Goal</option>
            <option value="credit">Credit</option>
          </select>
        </div>
        <div class="field" v-if="newKind === 'savings'">
          <label>Interest rate (APR %)</label>
          <input class="input mono" v-model="newApr" placeholder="4.0" />
        </div>
        <div class="field" v-if="newKind === 'goal'">
          <label>Target amount</label>
          <input class="input mono" v-model="newTarget" placeholder="5000" />
        </div>
        <div class="field" v-if="newKind === 'credit'">
          <label>Credit limit</label>
          <input class="input mono" v-model="newLimit" placeholder="1000" />
        </div>
        <div class="row">
          <button class="btn red" @click="createAccount">Open</button>
          <button class="btn ghost" @click="openNew = false">Cancel</button>
        </div>
      </div>
    </div>

    <div class="modal-backdrop" v-if="req" @click.self="req = null">
      <div class="card dialog">
        <div class="card-title">Requisites for transfers</div>
        <table class="data">
          <tbody>
            <tr><td class="muted">Holder</td><td>{{ req.owner_full_name }}</td></tr>
            <tr><td class="muted">Account</td><td class="mono">{{ req.account_id }} · {{ req.currency }}</td></tr>
            <tr><td class="muted">Bank</td><td>{{ req.bank }}</td></tr>
            <tr><td class="muted">BIC</td><td class="mono">{{ req.bic }}</td></tr>
            <tr><td class="muted">SWIFT</td><td class="mono">{{ req.swift }}</td></tr>
            <tr><td class="muted">Correspondent account</td><td class="mono">{{ req.correspondent_account }}</td></tr>
          </tbody>
        </table>
        <div class="row" style="margin-top:12px">
          <button class="btn sm ghost" @click="req = null">Close</button>
        </div>
      </div>
    </div>

    <div class="modal-backdrop" v-if="st" @click.self="st = null">
      <div class="card dialog">
        <div class="card-title">Account statement</div>
        <div class="field">
          <label>Period</label>
          <select class="select" v-model="period">
            <option value="week">Last week</option>
            <option value="month">Last month</option>
            <option value="custom">Custom</option>
          </select>
        </div>
        <div class="row" v-if="period === 'custom'">
          <input class="input mono" type="date" v-model="from" />
          <input class="input mono" type="date" v-model="to" />
        </div>
        <div class="field" style="margin-top:12px">
          <label>Columns</label>
          <div class="row" style="flex-wrap:wrap;gap:10px">
            <label v-for="f in FIELDS" :key="f" class="row" style="gap:4px;font-size:13px;cursor:pointer">
              <input type="checkbox" :value="f" v-model="selFields" /> {{ f }}
            </label>
          </div>
        </div>
        <div class="row" style="margin-top:12px">
          <a class="btn sm" :href="pdfUrl">Download PDF</a>
          <a class="btn sm ghost" :href="csvUrl">Download CSV</a>
        </div>
        <div class="row" style="margin-top:8px">
          <button class="btn sm ghost" @click="st = null">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const accounts = ref<any[]>([])
const error = ref('')
const openNew = ref(false)
const newCurrency = ref('USD')
const newKind = ref('current')
const newApr = ref('')
const newTarget = ref('')
const newLimit = ref('')

const KIND_LABELS: Record<string, string> = {
  current: 'Current accounts', savings: 'Savings', goal: 'Goals', credit: 'Credit',
}
const groups = computed(() => {
  const order = ['current', 'savings', 'goal', 'credit']
  return order
    .map((kind) => ({ kind, label: KIND_LABELS[kind], items: accounts.value.filter((x: any) => x.kind === kind) }))
    .filter((g) => g.items.length)
})
const req = ref<any>(null)
const st = ref<any>(null)
const period = ref('month')
const from = ref('')
const to = ref('')

function fmt(v: number) {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)
}

function isoDaysAgo(days: number): string {
  const d = new Date(Date.now() - days * 86400000)
  return d.toISOString().slice(0, 10)
}

const range = computed(() => {
  if (period.value === 'week') return { f: isoDaysAgo(7), t: isoDaysAgo(0) }
  if (period.value === 'month') return { f: isoDaysAgo(30), t: isoDaysAgo(0) }
  return { f: from.value, t: to.value }
})

const FIELDS = ['date', 'description', 'counterparty', 'amount', 'status']
const selFields = ref<string[]>([...FIELDS])

const pdfUrl = computed(() =>
  `/api/v1/accounts/${st.value?.id}/statement.pdf?from=${range.value.f}&to=${range.value.t}&fields=${selFields.value.join(',')}`)
const csvUrl = computed(() =>
  `/api/v1/accounts/${st.value?.id}/statement.csv?from=${range.value.f}&to=${range.value.t}&fields=${selFields.value.join(',')}`)

async function load() {
  accounts.value = await api('/api/v1/accounts')
}

async function createAccount() {
  error.value = ''
  const body: any = { currency: newCurrency.value, kind: newKind.value }
  if (newKind.value === 'savings' && newApr.value) body.apr = Number(newApr.value)
  if (newKind.value === 'goal') body.target_amount = Number(newTarget.value)
  if (newKind.value === 'credit') body.credit_limit = Number(newLimit.value)
  try {
    await api('/api/v1/accounts', { method: 'POST', body: JSON.stringify(body) })
    openNew.value = false
    await load()
  } catch (e: any) {
    error.value = e.message
  }
}

async function openRequisites(a: any) {
  error.value = ''
  try {
    req.value = await api(`/api/v1/accounts/${a.id}/requisites`)
  } catch (e: any) {
    error.value = e.message
  }
}

function openStatement(a: any) {
  st.value = a
  period.value = 'month'
}

async function closeAccount(a: any) {
  error.value = ''
  try {
    await api(`/api/v1/accounts/${a.id}/close`, { method: 'POST' })
    await load()
  } catch (e: any) {
    error.value = e.message
  }
}

onMounted(load)
</script>

<style scoped>
.err { color: var(--red); margin-top: 12px; }
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(20, 22, 27, 0.45);
  display: flex; align-items: center; justify-content: center; z-index: 40;
}
.modal { width: 480px; max-width: 92vw; }
.progress-track { height: 6px; border-radius: 999px; background: var(--bg); border: 1px solid var(--line); overflow: hidden; margin-top: 6px; }
.progress-fill { height: 100%; background: var(--red); }
.kindline { margin-top: 6px; font-size: 12px; }
</style>
