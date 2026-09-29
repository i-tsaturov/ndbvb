<template>
  <div class="page">
    <div class="page-head">
      <h1>Back office</h1>
      <span class="sub">operator console</span>
    </div>

    <div v-if="banner" class="card dark" style="margin-bottom:18px">
      <div class="mono" style="font-size:13px">{{ banner.banner }}</div>
    </div>

    <div class="card">
      <div class="card-title">Support queue</div>
      <table class="data">
        <thead><tr><th>#</th><th>Customer</th><th>Subject</th><th>Message</th><th>Status</th><th></th></tr></thead>
        <tbody>
          <tr v-if="!tickets.length"><td colspan="6" class="muted">Queue is empty</td></tr>
          <tr v-for="t in tickets" :key="t.id">
            <td class="mono">{{ t.id }}</td>
            <td class="mono">{{ t.user_id }}</td>
            <td>{{ t.subject }}</td>
            <td class="msg" v-html="t.message"></td>
            <td><span class="chip" :class="t.status === 'closed' ? '' : 'green'">{{ t.status }}</span></td>
            <td><button v-if="t.status !== 'closed'" class="btn sm" @click="close(t)">Close</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card" style="margin-top:18px">
      <div class="card-title">KYC verification</div>
      <table class="data">
        <thead><tr><th>User</th><th>Status</th><th>Documents</th><th></th></tr></thead>
        <tbody>
          <tr v-if="!kyc.length"><td colspan="4" class="muted">Queue is empty</td></tr>
          <tr v-for="k in kyc" :key="k.user_id">
            <td class="mono">{{ k.login }}</td>
            <td><span class="chip" :class="k.kyc_status === 'verified' ? 'green' : ''">{{ k.kyc_status }}</span></td>
            <td class="mono">{{ k.documents }}</td>
            <td style="text-align:right">
              <button v-if="k.kyc_status !== 'verified'" class="btn sm" @click="verifyKyc(k)">Verify</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card" style="margin-top:18px">
      <div class="card-title">Customers</div>
      <table class="data">
        <thead><tr><th>ID</th><th>Login</th><th>Name</th><th>Phone</th><th>Risk</th><th>Accounts</th></tr></thead>
        <tbody>
          <tr v-for="c in customers" :key="c.id">
            <td class="mono">{{ c.id }}</td>
            <td class="mono">{{ c.login }}</td>
            <td>{{ c.name }}</td>
            <td class="mono">{{ c.phone }}</td>
            <td><span class="chip" :class="c.risk >= 4 ? 'red' : ''">{{ c.risk }}</span></td>
            <td class="mono" style="font-size:12px">
              <div v-for="a in c.accounts" :key="a.id">{{ a.id }}: {{ a.balance }} {{ a.currency }}</div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { useAuth } from '../stores/auth'

const auth = useAuth()
const banner = ref<any>(null)
const tickets = ref<any[]>([])
const customers = ref<any[]>([])
const kyc = ref<any[]>([])

async function verifyKyc(k: any) {
  await api(`/api/v1/admin/kyc/${k.user_id}/verify`, { method: 'POST' })
  k.kyc_status = 'verified'
}

async function close(t: any) {
  await api(`/api/v1/support/tickets/${t.id}/close`, { method: 'POST' })
  t.status = 'closed'
}

onMounted(async () => {
  if (!auth.isBackoffice) {
  }
  try {
    banner.value = await api('/api/v1/admin/console-banner')
  } catch {
    banner.value = null
  }
  try {
    tickets.value = await api('/api/v1/admin/tickets')
    customers.value = (await api('/api/v1/admin/customers')).customers
    kyc.value = await api('/api/v1/admin/kyc-queue')
  } catch {
  }
})
</script>
