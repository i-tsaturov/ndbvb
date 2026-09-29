<template>
  <div class="page">
    <div class="page-head">
      <h1>Cards &amp; rewards</h1>
      <span class="sub">manage your cards and cashback</span>
    </div>

    <div v-for="c in cards" :key="'cb-' + c.id" class="card" style="margin-bottom:12px">
      <div class="spread">
        <div class="card-title" style="margin:0">Cashback · card {{ c.id }}</div>
        <span class="chip green">earned {{ fmt(c.cashbackEarned) }} {{ c.currency }}</span>
      </div>
      <div class="row" style="flex-wrap:wrap;margin-top:8px">
        <span v-for="k in c.campaigns" :key="k.id" class="row" style="gap:6px;margin:2px">
          <span class="chip">{{ k.title }} {{ k.percent }}%</span>
          <span v-if="k.active" class="chip green">Active</span>
          <button v-else class="btn sm ghost" @click="activate(k, c)">Activate</button>
        </span>
      </div>
    </div>

    <template>
      <div class="grid cols-2">
        <div class="card hoverable" v-for="c in cards" :key="c.id" :class="{ closed: c.status === 'closed' }">
          <div class="spread">
            <div class="card-title" style="margin:0">{{ c.kind }}{{ c.currency ? ' · ' + c.currency : '' }}{{ c.virtual ? ' · virtual' : '' }}</div>
            <span class="chip" :class="c.status === 'active' ? 'green' : c.status === 'blocked' ? '' : ''">{{ c.status }}</span>
          </div>
          <div class="pan mono">{{ displayPan(c) }}</div>
          <div class="row spread" style="margin-top:14px">
            <div>
              <div class="muted" style="font-size:11px">HOLDER</div>
              <div class="mono" style="font-size:13px">{{ c.holder }}</div>
            </div>
            <div>
              <div class="muted" style="font-size:11px">EXPIRES</div>
              <div class="mono" style="font-size:13px">{{ c.expiry }}</div>
            </div>
          </div>
          <div class="row" style="margin-top:12px; flex-wrap:wrap">
            <button class="btn sm ghost" v-if="c.status !== 'closed'" @click="freeze(c)">
              {{ c.frozen ? 'Unblock' : 'Block' }}
            </button>
            <button class="btn sm" v-if="revealed.has(c.id)" @click="hidePan(c)">Hide number</button>
            <button class="btn sm ghost" v-else-if="c.status !== 'closed'" @click="revealPan(c)">Show number</button>
            <button class="btn sm ghost" style="color:var(--red)" v-if="c.status !== 'closed'" @click="askClose(c)">Close card</button>
          </div>
          <div v-if="revealed.has(c.id)" class="mono fullpan">{{ c.pan }} · CVV {{ c.cvv }}</div>
        </div>

        <div class="order-tile" style="display:flex;align-items:center;justify-content:center">
          <button class="btn ghost" @click="orderOpen = true">Order new card</button>
        </div>
      </div>
    </template>

    <div class="modal-backdrop" v-if="orderOpen" @click.self="orderOpen = false">
      <div class="card dialog">
        <div class="card-title">Order a new card</div>
        <div class="field">
          <label>Type</label>
          <select class="select" v-model="order.kind">
            <option value="debit">Debit</option>
            <option value="credit">Credit</option>
          </select>
        </div>
        <div class="field">
          <label>Currency</label>
          <select class="select" v-model="order.currency">
            <option>USD</option><option>EUR</option><option>GHS</option>
          </select>
        </div>
        <label class="row" style="cursor:pointer;font-size:14px;margin-bottom:14px">
          <input type="checkbox" v-model="order.virtual" /> Virtual (issued instantly)
        </label>
        <div class="row">
          <button class="btn red" @click="orderCard">Order</button>
          <button class="btn ghost" @click="orderOpen = false">Cancel</button>
        </div>
      </div>
    </div>

    <div class="modal-backdrop" v-if="closing" @click.self="closing = null">
      <div class="card dialog">
        <div class="card-title">Close card {{ closing.id }}</div>
        <p class="muted" style="font-size:13px">
          This is permanent. Confirm with the code we sent by SMS
          (read it on the <a :href="gwUrl" target="_blank">gateway</a>).
        </p>
        <div class="field">
          <label>Confirmation code</label>
          <input class="input mono" v-model="closeCode" maxlength="4" placeholder="SMS code" />
        </div>
        <div class="row">
          <button class="btn red" :disabled="closeCode.length !== 4" @click="doClose">Close card</button>
          <button class="btn ghost" @click="closing = null">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const gwUrl = `http://${window.location.hostname}:9500`
const cards = ref<any[]>([])
const revealed = ref(new Set<number>())
const orderOpen = ref(false)
const order = ref({ kind: 'debit', currency: 'USD', virtual: true })
const closing = ref<any>(null)
const closeCode = ref('')

function mask(pan: string) {
  return pan.slice(0, 6) + '\u00A0\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u00A0' + pan.slice(-4)
}
function displayPan(c: any) {
  return revealed.value.has(c.id) ? c.pan : mask(c.pan)
}
function revealPan(c: any) {
  revealed.value.add(c.id)
  revealed.value = new Set(revealed.value)
}
function hidePan(c: any) {
  revealed.value.delete(c.id)
  revealed.value = new Set(revealed.value)
}

function fmt(v: number) {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v || 0)
}

async function load() {
  cards.value = await api('/api/v1/cards')
  for (const card of cards.value) {
    try {
      const cb = await api(`/api/v1/cards/${card.id}/cashback`)
      card.cashbackEarned = cb.earned
      card.campaigns = cb.campaigns || []
    } catch {
      card.cashbackEarned = 0
      card.campaigns = []
    }
  }
}

async function freeze(c: any) {
  try {
    const res = await api(`/api/v1/cards/${c.id}/freeze`, { method: 'POST' })
    c.frozen = res.frozen
    c.status = res.status
  } catch (e: any) {
    alert(e.message)
  }
}

async function orderCard() {
  await api('/api/v1/cards', {
    method: 'POST',
    body: JSON.stringify({ currency: order.value.currency, kind: order.value.kind, virtual: order.value.virtual }),
  })
  orderOpen.value = false
  await load()
}

async function askClose(c: any) {
  closeCode.value = ''
  closing.value = c
}

async function doClose() {
  const res = await api(`/api/v1/cards/${closing.value.id}/close`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
  closing.value.status = res.status
  closing.value.closed = true
  closing.value = null
}

async function activate(k: any, card: any) {
  try {
    await api(`/api/v1/cashback/campaigns/${k.id}/activate`, {
      method: 'POST',
      body: JSON.stringify({ card_id: card.id }),
    })
    await load()
  } catch (e: any) {
    alert(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
.tabs { flex-wrap: wrap; }
.pan { font-size: 22px; letter-spacing: 0.08em; margin-top: 16px; }
.card.closed { opacity: 0.55; }
.order-tile {
  min-height: 190px; border: 1px dashed var(--line); border-radius: 12px;
}
.fullpan { margin-top: 10px; font-size: 13px; color: var(--red); }
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(20, 22, 27, 0.45);
  display: flex; align-items: center; justify-content: center; z-index: 40;
}
.modal { width: 420px; max-width: 92vw; }
</style>
