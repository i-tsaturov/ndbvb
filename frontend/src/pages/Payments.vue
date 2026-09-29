<template>
  <div class="page">
    <div class="page-head">
      <h1>Payments</h1>
      <span class="sub">transfers between your accounts, to OnlineBank customers and cards</span>
    </div>

    <div class="card" v-if="step === 'form'">
      <div class="row tabs">
        <button v-for="t in TYPES" :key="t.id" class="btn sm" :class="{ ghost: type !== t.id }" @click="type = t.id">
          {{ t.label }}
        </button>
      </div>

      <div class="field">
        <label>From account</label>
        <select class="select" v-model="from">
          <option v-for="a in accounts" :key="a.id" :value="a.id">
            {{ a.id }} · {{ fmt(a.balance) }} {{ a.currency }}
          </option>
        </select>
      </div>

      <template v-if="type === 'internal'">
        <div class="field">
          <label>To account (your own)</label>
          <select class="select" v-model="toAccount">
            <option v-for="a in accounts.filter(x => x.id !== from)" :key="a.id" :value="a.id">
              {{ a.id }} · {{ a.currency }}
            </option>
          </select>
        </div>
      </template>

      <template v-else>
        <div class="field">
          <label>Recipient</label>
          <div class="row">
            <select class="select" style="width:120px" v-model="channel" v-if="type !== 'card2card'">
              <option value="phone">Phone</option>
              <option value="card">Card</option>
              <option value="account">Account</option>
            </select>
            <input class="input mono" style="flex:1" v-model="recipientInput"
                   :placeholder="type === 'card2card' ? 'Card number' : 'Phone, card or account'" />
            <span v-if="type === 'card2card' || channel === 'card'" :class="luhnState === '✓' ? 'pan-valid' : 'pan-invalid'">{{ luhnState }}</span>
          </div>
          <span class="hint">the bank identifies the recipient automatically as you type</span>
        </div>
        <div v-if="recipient" class="lookup-card">
          <b>{{ recipient.masked_name }}</b> · {{ recipient.bank }}
        </div>
        <div v-else-if="lookupError" class="lookup-card err-card">{{ lookupError }}</div>
        <p v-if="type === 'card2card'" class="hint" style="margin-bottom:12px">Fee 1% for transfers to cards. Enter the recipient card number below.</p>
      </template>

      <div class="field">
        <label>Amount</label>
        <input class="input mono" v-model="amount" placeholder="100.00" />
      </div>
      <div class="field">
        <label>Message to recipient</label>
        <input class="input" v-model="description" placeholder="Dinner split" />
      </div>
      <button class="btn red" :disabled="busy || !ready" @click="create">{{ busy ? 'Checking…' : 'Continue' }}</button>
      <p v-if="error" class="err">{{ error }}</p>
    </div>

    <div class="card" v-if="step === 'confirm' && preview">
      <div class="card-title">Review the payment</div>
      <table class="data">
        <tbody>
          <tr><td class="muted">Amount</td><td class="mono r">{{ fmt(preview.amount) }} {{ preview.currency }}</td></tr>
          <tr><td class="muted">Fee{{ type === 'card2card' ? ' 1%' : '' }}</td><td class="mono r">{{ fmt(preview.fee) }} {{ preview.currency }}</td></tr>
          <tr><td class="muted">Total debited</td><td class="mono r"><b>{{ fmt(preview.total_debit) }} {{ preview.currency }}</b></td></tr>
          <tr><td class="muted">Recipient</td><td>{{ preview.masked_name }} · OnlineBank</td></tr>
          <tr><td class="muted">From</td><td class="mono">account {{ from }}</td></tr>
        </tbody>
      </table>

      <div class="field" style="margin-top:16px">
        <label>Confirmation code</label>
        <div class="row">
          <button class="btn sm ghost" @click="sendCode" :disabled="codeSent">{{ codeSent ? 'Code sent' : 'Send code' }}</button>
          <input class="input mono" style="width:120px" v-model="code" maxlength="4" placeholder="1234" />
        </div>
        <span class="hint">the code arrives by SMS · didn't get it? <a :href="gwUrl" target="_blank">SMS gateway</a></span>
      </div>
      <div class="row">
        <button class="btn red" :disabled="!code" @click="confirm">Confirm</button>
        <button class="btn ghost" @click="step = 'form'">Back</button>
      </div>
      <p v-if="error" class="err">{{ error }}</p>
    </div>

    <div class="card" v-if="step === 'processing'">
      <div class="card-title">Processing</div>
      <p>Operation <span class="mono">#{{ paymentId }}</span> is accepted and waits for the settlement processor.</p>
      <button class="btn" @click="runProcessing">Run processing</button>
      <button class="btn ghost" @click="backToForm">New payment</button>
      <p v-if="error" class="err">{{ error }}</p>
    </div>

    <div class="card receipt" v-if="step === 'receipt' && receipt">
      <div class="card-title">Payment receipt</div>
      <table class="data">
        <tbody>
          <tr><td class="muted">Operation No</td><td class="mono">{{ receipt.payment_id }}</td></tr>
          <tr><td class="muted">Status</td>
              <td><span class="chip" :class="receipt.status === 'executed' ? 'green' : receipt.status === 'rejected' ? 'red' : ''">{{ receipt.status }}</span></td></tr>
          <tr><td class="muted">Date</td><td class="mono">{{ (receipt.executed_at || receipt.created_at || '').replace('T', ' ').slice(0, 19) }}</td></tr>
          <tr><td class="muted">Amount</td><td class="mono">{{ fmt(receipt.amount) }} {{ receipt.currency }}</td></tr>
          <tr><td class="muted">Fee</td><td class="mono">{{ fmt(receipt.fee) }} {{ receipt.currency }}</td></tr>
          <tr><td class="muted">Recipient</td><td>{{ receipt.masked_name }} · OnlineBank</td></tr>
          <tr v-if="receipt.reject_reason"><td class="muted">Reject reason</td><td class="err-inline">{{ receipt.reject_reason }}</td></tr>
          <tr v-if="receipt.description"><td class="muted">Message</td><td>{{ receipt.description }}</td></tr>
        </tbody>
      </table>
      <div class="row" style="margin-top:14px; flex-wrap: wrap">
        <button class="btn sm" @click="print">Print receipt</button>
        <a class="btn sm ghost" :href="`/api/v1/payments/${receipt.payment_id}/receipt.pdf`">Download PDF</a>
        <button class="btn sm ghost" @click="saveTemplate" v-if="!templateSaved">Save as template</button>
        <span v-if="!templateSaved && savingTpl" class="row" style="gap:6px">
          <input class="input" style="width:160px" v-model="tplName" placeholder="Template name" />
          <button class="btn sm" @click="submitTemplate">Save</button>
        </span>
        <button class="btn sm ghost" @click="backToForm">New payment</button>
      </div>
      <p v-if="templateSaved" class="okmsg">Template saved</p>
    </div>

    <div class="card" style="margin-top:18px" v-if="step === 'form'">
      <div class="card-title">Recent payments</div>
      <table class="data">
        <thead><tr><th>#</th><th>Type</th><th>Status</th><th class="r">Amount</th><th>Recipient</th></tr></thead>
        <tbody>
          <tr v-if="!recent.length"><td colspan="5" class="muted">No payments yet</td></tr>
          <tr v-for="p in recent" :key="p.payment_id" style="cursor:pointer" @click="showReceipt(p.payment_id)">
            <td class="mono">{{ p.payment_id }}</td>
            <td>{{ p.type }}</td>
            <td><span class="chip" :class="p.status === 'executed' ? 'green' : p.status === 'rejected' ? 'red' : ''">{{ p.status }}</span></td>
            <td class="mono r">{{ fmt(p.amount) }} {{ p.currency }}</td>
            <td>{{ p.masked_name }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'

const TYPES = [
  { id: 'internal', label: 'Between my accounts' },
  { id: 'customer', label: 'To OnlineBank customer' },
  { id: 'card2card', label: 'To card' },
]

const gwUrl = `http://${window.location.hostname}:9500`
const step = ref<'form' | 'confirm' | 'processing' | 'receipt'>('form')
const type = ref('internal')
const accounts = ref<any[]>([])
const from = ref<number | null>(null)
const toAccount = ref<number | null>(null)
const channel = ref('phone')
const recipientValue = ref('')
const recipientInput = ref('')
const recipient = ref<any>(null)
const lookupError = ref('')
let lookupTimer: any = null

function luhnOk(pan: string): boolean {
  const digits = pan.replace(/\D/g, '')
  if (digits.length !== 16) return false
  let total = 0
  for (let i = 0; i < digits.length; i++) {
    let d = Number(digits[digits.length - 1 - i])
    if (i % 2 === 1) { d *= 2; if (d > 9) d -= 9 }
    total += d
  }
  return total % 10 === 0
}

const luhnState = computed(() => {
  const digits = recipientInput.value.replace(/\D/g, '')
  if (!digits.length) return ''
  if (digits.length < 16) return '…'
  return luhnOk(digits) ? '✓' : '✗'
})

function scheduleLookup() {
  if (lookupTimer) clearTimeout(lookupTimer)
  recipient.value = null
  lookupError.value = ''
  const raw = recipientInput.value.trim()
  if (!raw) return
  const isCard = type.value === 'card2card' || channel.value === 'card'
  if (isCard) {
    const digits = raw.replace(/\D/g, '')
    if (digits.length !== 16) return
    if (!luhnOk(digits)) { lookupError.value = 'Invalid card number'; return }
  } else if (channel.value === 'phone' && raw.length < 9) return
  else if (channel.value === 'account' && !/^\d{3,}$/.test(raw)) return
  lookupTimer = setTimeout(doLookup, 500)
}

watch([recipientInput, channel, type], scheduleLookup)

watch(recipientInput, (v) => {
  if (type.value === 'card2card' || channel.value === 'card') {
    const digits = v.replace(/\D/g, '').slice(0, 16)
    const formatted = digits.replace(/(\d{4})(?=\d)/g, '$1 ')
    if (formatted !== v) recipientInput.value = formatted
    recipientValue.value = digits
  } else {
    recipientValue.value = v
  }
})
const amount = ref('')
const description = ref('')
const preview = ref<any>(null)
const paymentId = ref<number | null>(null)
const code = ref('')
const codeSent = ref(false)
const receipt = ref<any>(null)
const recent = ref<any[]>([])
const busy = ref(false)
const error = ref('')
const templateSaved = ref(false)

function fmt(v: number) {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)
}

const ready = computed(() => {
  if (!from.value || !amount.value) return false
  if (type.value === 'internal') return !!toAccount.value
  return recipientValue.value.trim().length > 0
})  // lookup happens automatically; typing alone enables Continue

async function load() {
  accounts.value = await api('/api/v1/accounts')
  from.value = accounts.value[0]?.id ?? null
  toAccount.value = accounts.value[1]?.id ?? null
  recent.value = await api('/api/v1/payments')
}

async function doLookup() {
  try {
    recipient.value = await api('/api/v1/payments/lookup', {
      method: 'POST',
      body: JSON.stringify({
        channel: type.value === 'card2card' ? 'card' : channel.value,
        value: recipientValue.value,
      }),
    })
  } catch (e: any) {
    lookupError.value = e.message
  }
}

async function create() {
  busy.value = true
  error.value = ''
  templateSaved.value = false
  try {
    const body: any = { type: type.value, from_account: from.value, amount: amount.value, description: description.value }
    if (type.value === 'internal') body.to_account = toAccount.value
    else {
      body.channel = type.value === 'card2card' ? 'card' : channel.value
      body.value = recipientValue.value
      body.to_account = recipient.value?.account_id
    }
    const res = await api('/api/v1/payments/transfer', { method: 'POST', body: JSON.stringify(body) })
    preview.value = res.preview
    paymentId.value = res.payment_id
    step.value = 'confirm'
    code.value = ''
    codeSent.value = false
  } catch (e: any) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function sendCode() {
  await api(`/api/v1/payments/${paymentId.value}/otp`, { method: 'POST' })
  codeSent.value = true
}

async function confirm() {
  error.value = ''
  try {
    const res = await api(`/api/v1/payments/${paymentId.value}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ code: code.value }),
    })
    if (res.status === 'executed') {
      receipt.value = res
      step.value = 'receipt'
    } else {
      step.value = 'processing'
    }
    recent.value = await api('/api/v1/payments')
  } catch (e: any) {
    error.value = e.message
  }
}

async function runProcessing() {
  error.value = ''
  try {
    receipt.value = await api(`/api/v1/payments/${paymentId.value}/execute`, { method: 'POST' })
    step.value = 'receipt'
    recent.value = await api('/api/v1/payments')
  } catch (e: any) {
    error.value = e.message
  }
}

async function showReceipt(id: number) {
  receipt.value = await api(`/api/v1/payments/${id}`)
  step.value = 'receipt'
}

function print() {
  window.print()
}

const tplName = ref('')
const savingTpl = ref(false)

function saveTemplate() {
  savingTpl.value = true
}

async function submitTemplate() {
  if (!tplName.value || !paymentId.value) return
  await api('/api/v1/templates', {
    method: 'POST',
    body: JSON.stringify({ payment_id: paymentId.value, name: tplName.value }),
  })
  templateSaved.value = true
  savingTpl.value = false
}

function backToForm() {
  step.value = 'form'
  recipient.value = null
  recipientValue.value = ''
  amount.value = ''
  description.value = ''
  load()
}

onMounted(load)
</script>

<style scoped>
.tabs { margin-bottom: 16px; flex-wrap: wrap; }
.lookup-card { transition: opacity .2s; }
.pan-valid { color: #1E7A2E; font-family: var(--mono); }
.pan-invalid { color: var(--red); font-family: var(--mono); }
.err-card { background: #FFF5F5; border-color: #F2C1C1; }
.lookup-card {
  background: #F2FBF3; border: 1px solid #BFE3C0; border-radius: 8px;
  padding: 8px 12px; font-size: 14px; margin-bottom: 12px;
}
.err { color: var(--red); margin-top: 10px; }
.err-inline { color: var(--red); }
.okmsg { color: #1E7A2E; margin-top: 8px; font-size: 13px; }
.r { text-align: right; }
</style>
