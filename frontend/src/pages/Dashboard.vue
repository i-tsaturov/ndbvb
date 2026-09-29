<template>
  <div class="page">
    <div class="page-head">
      <h1>Overview</h1>
      <span class="sub">every action on this screen is an API call</span>
    </div>

    <div v-if="loading" class="grid cols-3">
      <div class="card" v-for="i in 3"><div class="skeleton" style="height:64px"></div></div>
    </div>

    <template v-else>
      <div class="grid cols-3">
        <div class="card dark hoverable" v-for="a in accounts" :key="a.id">
          <div class="card-title">{{ kindLabel(a.kind) }} · {{ a.id }}</div>
          <div class="big-number">{{ fmt(a.balance) }} <span class="cur">{{ a.currency }}</span></div>
        </div>
        <div class="card hoverable actions">
          <div class="card-title">Quick actions</div>
          <div class="stack">
            <router-link class="btn sm" to="/payments">New payment</router-link>
            <router-link class="btn sm ghost" to="/exchange">Exchange currency</router-link>
            <router-link class="btn sm ghost" to="/statements">Statements</router-link>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top:18px">
        <div class="spread" style="margin-bottom:8px">
          <div class="card-title" style="margin:0">Recent activity</div>
          <div class="row">
            <span v-for="a in accounts" :key="a.id" class="chip feed"
                  :class="{ on: a.id === mainFeed }"
                  style="cursor:pointer" @click="mainFeed = a.id">
              {{ kindLabel(a.kind) }} · {{ a.id }}
            </span>
          </div>
        </div>
        <table class="data">
          <thead>
            <tr><th>Date</th><th>Direction</th><th class="r">Amount</th><th>Description</th><th>Counterparty</th></tr>
          </thead>
          <tbody>
            <tr v-if="!txs.length"><td colspan="5" class="muted">No transactions</td></tr>
            <tr v-for="t in txs" :key="t.id">
              <td class="mono muted">{{ short(t.ts) }}</td>
              <td>
                <span class="chip" :class="t.direction === 'credit' ? 'green' : ''">{{ t.direction }}</span>
                <span v-if="t.status === 'cancelled'" class="chip red">{{ t.status }}</span>
              </td>
              <td class="mono r" :class="{ credit: t.direction === 'credit' }">
                {{ t.direction === 'credit' ? '+' : '' }}{{ fmt(t.amount) }} {{ t.currency }}
              </td>
              <td class="desc" v-html="t.description"></td>
              <td class="muted">{{ t.counterparty }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api, fmtMoney } from '../api'

const accounts = ref<any[]>([])
const txs = ref<any[]>([])
const mainFeed = ref<number | null>(null)
const loading = ref(true)

function fmt(v: number) {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)
}
function kindLabel(kind: string) {
  return { current: 'Everyday', savings: 'Savings', goal: 'Goal', credit: 'Credit' }[kind] || kind
}
function short(ts: string) {
  return (ts || '').replace('T', ' ').slice(0, 16)
}

async function loadFeed() {
  if (!mainFeed.value) return
  const res = await api(`/api/v1/accounts/${mainFeed.value}/transactions?limit=15`)
  txs.value = res.transactions
}

watch(mainFeed, (nv, ov) => {
  if (ov !== null) loadFeed()
})

async function loadMe() {
  const query = `query { me { id login firstName lastName
    accounts { id currency balance kind status }
    recentTransactions(limit: 15) { id ts direction amount currency
      description counterparty status accountId } } }`
  const res = await api('/api/v1/graphql', { method: 'POST', body: JSON.stringify({ query }) })
  const me = res.data.me
  accounts.value = me.accounts
  txs.value = me.recentTransactions
  mainFeed.value = me.accounts[0]?.id ?? null
  loading.value = false
}

onMounted(loadMe)
</script>

<style scoped>
.r { text-align: right; }
td.credit { color: #1E7A2E; }
.actions .stack { margin-top: 4px; }
.actions a { text-decoration: none; }
.chip.feed.on {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}
</style>
