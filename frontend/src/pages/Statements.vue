<template>
  <div class="page">
    <div class="page-head">
      <h1>Statements</h1>
      <span class="sub">search, export and import</span>
    </div>

    <div class="card">
      <div class="card-title">Search transactions</div>
      <div class="row" style="flex-wrap:wrap;gap:12px;margin-bottom:14px">
        <select class="select" style="width:260px" v-model="accountId" @change="load">
          <option v-for="a in accounts" :key="a.id" :value="a.id">
            {{ a.name }} · {{ a.number }}
          </option>
        </select>
        <input class="input" style="width:260px" v-model="search" placeholder="Search description / counterparty" @keyup.enter="load" />
        <select class="select" style="width:180px" v-model="sort" @change="load">
          <option value="">Newest first</option>
          <option value="ts ASC">Oldest first</option>
          <option value="amount DESC">Largest first</option>
        </select>
        <button class="btn sm" @click="load">Search</button>
      </div>
      <table class="data">
        <thead>
          <tr><th>Date</th><th class="r">Amount</th><th>Description</th><th>Counterparty</th><th>Status</th></tr>
        </thead>
        <tbody>
          <tr v-if="!rows.length"><td colspan="5" class="muted">Nothing found</td></tr>
          <tr v-for="t in rows" :key="t.id">
            <td class="mono muted">{{ (t.ts || '').replace('T', ' ').slice(0, 16) }}</td>
            <td class="mono r">{{ t.direction === 'credit' ? '+' : '' }}{{ t.amount }} {{ t.currency }}</td>
            <td class="desc" v-html="t.description"></td>
            <td class="muted">{{ t.counterparty }}</td>
            <td><span class="chip" :class="t.status === 'cancelled' ? 'red' : 'green'">{{ t.status }}</span></td>
          </tr>
        </tbody>
      </table>
      <p v-if="error" class="err">{{ error }}</p>
    </div>

    <div class="grid cols-2" style="margin-top:18px">
      <div class="card">
        <div class="card-title">Export statement</div>
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
        <div class="field" style="margin-top:10px">
          <label>Columns</label>
          <div class="row" style="flex-wrap:wrap;gap:10px">
            <label v-for="f in FIELDS" :key="f" class="row" style="gap:4px;font-size:13px;cursor:pointer">
              <input type="checkbox" :value="f" v-model="selFields" /> {{ f }}
            </label>
          </div>
        </div>
        <div class="row">
          <a class="btn sm" :href="pdfUrl">Download PDF</a>
          <a class="btn sm ghost" :href="csvUrl">Download CSV</a>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Import corporate statement</div>
        <p class="muted" style="font-size:13px;margin-bottom:12px">
          For legacy desktop accounting tools: XML format, or binary .bnk format.
        </p>
        <input type="file" @change="e => (file = (e.target as any).files?.[0])" />
        <button class="btn sm" style="margin-top:12px" :disabled="!file || busy" @click="doImport">
          {{ busy ? 'Importing…' : 'Upload' }}
        </button>
        <pre v-if="importResult" class="mono" style="margin-top:12px;font-size:12px;white-space:pre-wrap">{{ JSON.stringify(importResult, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const FIELDS = ['date', 'description', 'counterparty', 'amount', 'status']

const accounts = ref<any[]>([])
const accountId = ref<number | null>(null)
const search = ref('')
const sort = ref('')
const rows = ref<any[]>([])
const error = ref('')
const period = ref('month')
const from = ref('')
const to = ref('')
const selFields = ref<string[]>([...FIELDS])
const file = ref<File | null>(null)
const busy = ref(false)
const importResult = ref<any>(null)

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 86400000).toISOString().slice(0, 10)
}

const range = computed(() => {
  if (period.value === 'week') return { f: isoDaysAgo(7), t: isoDaysAgo(0) }
  if (period.value === 'month') return { f: isoDaysAgo(30), t: isoDaysAgo(0) }
  return { f: from.value, t: to.value }
})

const pdfUrl = computed(() =>
  `/api/v1/accounts/${accountId.value}/statement.pdf?from=${range.value.f}&to=${range.value.t}&fields=${selFields.value.join(',')}`)
const csvUrl = computed(() =>
  `/api/v1/accounts/${accountId.value}/statement.csv?from=${range.value.f}&to=${range.value.t}&fields=${selFields.value.join(',')}`)

async function load() {
  error.value = ''
  try {
    const params = new URLSearchParams({ search: search.value, sort: sort.value, limit: '100' })
    const res = await api(`/api/v1/accounts/${accountId.value}/transactions?${params}`)
    rows.value = res.transactions
  } catch (e: any) {
    error.value = e.message
    rows.value = []
  }
}

async function doImport() {
  if (!file.value) return
  busy.value = true
  importResult.value = null
  try {
    const form = new FormData()
    form.append('file', file.value)
    const res = await fetch('/api/v1/statements/import', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + localStorage.getItem('ob_token') },
      body: form,
    })
    importResult.value = await res.json()
  } catch (e: any) {
    importResult.value = { error: e.message }
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  accounts.value = await api('/api/v1/accounts')
  const everyday = accounts.value.find((a: any) => a.kind === 'current') || accounts.value[0]
  accountId.value = everyday?.id ?? null
  await load()
})
</script>

<style scoped>
.r { text-align: right; }
.err { color: var(--red); margin-top: 10px; }
</style>
