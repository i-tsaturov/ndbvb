<template>
  <div class="page">
    <div class="page-head">
      <h1>Profile</h1>
      <span class="sub">personal data, security and documents</span>
    </div>

    <div class="grid cols-2">
      <div class="stack" style="gap:18px">
        <div class="card">
          <div class="card-title">Personal data</div>
          <div class="row" style="gap:14px;margin-bottom:16px;align-items:center">
            <div class="avatar" :style="avatarStyle">{{ initials }}</div>
            <div>
              <div style="font-weight:600">{{ profile.first_name }} {{ profile.last_name }}</div>
              <label class="upload-label">
                <input type="file" accept="image/*" @change="onAvatarFile" hidden />
                <span class="btn sm ghost">Change photo</span>
              </label>
              <span v-if="avatarErr" class="errmsg" style="margin:6px 0 0">{{ avatarErr }}</span>
            </div>
          </div>
          <div class="field">
            <label>First name</label>
            <input class="input" v-model="profile.first_name" />
          </div>
          <div class="field">
            <label>Last name</label>
            <input class="input" v-model="profile.last_name" />
          </div>
          <div class="field">
            <label>Phone</label>
            <div class="row">
              <input class="input mono" v-model="profile.phone" disabled />
              <button class="btn sm ghost" @click="phoneOpen = true">Change</button>
            </div>
          </div>
          <div class="field">
            <label>Daily transfer limit</label>
            <input class="input mono" :value="profile.daily_limit" disabled />
            <span class="hint">changed by the branch on request</span>
          </div>
          <button class="btn red" :disabled="busy" @click="save">{{ busy ? 'Saving…' : 'Save' }}</button>
        </div>

        <div class="card">
          <div class="card-title">Promo code</div>
          <div class="row">
            <input class="input mono" v-model="promo" placeholder="WELCOME10" />
            <button class="btn sm" @click="applyPromo">Apply</button>
          </div>
          <p v-if="promoResult" class="mono" :class="promoResult.ok ? 'okmsg' : 'errmsg'">{{ promoResult.text }}</p>
        </div>
      </div>

      <div class="stack" style="gap:18px">
        <div class="card">
          <div class="spread">
            <div class="card-title" style="margin:0">Identity verification</div>
            <span class="chip" :class="profile.kyc_status === 'verified' ? 'green' : profile.kyc_status === 'pending' ? '' : 'red'">
              {{ kycLabel }}
            </span>
          </div>
          <p class="muted" style="font-size:13px;margin:10px 0 14px">
            Upload a passport or residence permit to enable international transfers.
          </p>
          <label class="dropzone">
            <input type="file" multiple @change="onKycFile" hidden />
            <div class="dz-title">Upload documents</div>
            <div class="muted" style="font-size:12px">Passport, driver's licence or national ID. PDF or images, up to 10 MB</div>
          </label>
          <p v-if="kycErr" class="errmsg">{{ kycErr }}</p>
          <table class="data" style="margin-top:12px">
            <tbody>
              <tr v-for="d in docs" :key="d.id">
                <td><a class="mono" style="font-size:13px" :href="d.url" target="_blank">{{ d.filename }}</a></td>
                <td class="mono muted" style="font-size:12px">{{ (d.uploaded_at || '').replace('T', ' ').slice(0, 16) }}</td>
              </tr>
              <tr v-if="!docs.length"><td class="muted">No documents uploaded</td></tr>
            </tbody>
          </table>
          <button class="btn sm" style="margin-top:12px" @click="submitKyc">
            Submit for verification
          </button>
          <p v-if="kycResult" class="okmsg">{{ kycResult }}</p>
        </div>
      </div>
    </div>

    <div class="modal-backdrop" v-if="phoneOpen" @click.self="phoneOpen = false">
      <div class="card dialog">
        <div class="card-title">Change phone number</div>
        <div class="field">
          <label>New number</label>
          <input class="input mono" v-model="newPhone" placeholder="+233..." />
        </div>
        <p class="muted" style="font-size:13px">
          We will send a confirmation code to your current number {{ maskPhone(profile.phone) }}.
        </p>
        <div class="field">
          <label>Code</label>
          <div class="row">
            <button class="btn sm ghost" @click="sendPhoneCode" :disabled="phoneSent">{{ phoneSent ? 'Code sent' : 'Send code' }}</button>
            <input class="input mono" style="width:110px" v-model="phoneCode" maxlength="4" placeholder="1234" />
          </div>
        </div>
        <div class="row">
          <button class="btn red" :disabled="!phoneCode || !newPhone" @click="confirmPhone">Confirm</button>
          <button class="btn ghost" @click="phoneOpen = false">Cancel</button>
        </div>
        <p v-if="phoneErr" class="errmsg">{{ phoneErr }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const profile = ref<any>({})
const busy = ref(false)
const promo = ref('')
const promoResult = ref<any>(null)
const docs = ref<any[]>([])
const kycResult = ref('')
const kycErr = ref('')
const avatarErr = ref('')
const phoneOpen = ref(false)
const newPhone = ref('')
const phoneCode = ref('')
const phoneSent = ref(false)
const phoneErr = ref('')

const initials = computed(() =>
  ((profile.value.first_name || '?')[0] + (profile.value.last_name || '')[0] || '').toUpperCase())
const avatarStyle = computed(() =>
  profile.value.avatar
    ? { background: `center/cover url(${profile.value.avatar})` }
    : { background: 'var(--ink)', color: '#fff' })
const kycLabel = computed(() =>
  ({ not_verified: 'Not verified', pending: 'Pending review', verified: 'Verified' } as any)[profile.value.kyc_status] || profile.value.kyc_status)

function maskPhone(p: string) {
  return p && p.length > 4 ? p.slice(0, -4).replace(/[0-9]/g, '*') + p.slice(-4) : p
}

async function load() {
  profile.value = await api('/api/v1/profile')
  docs.value = await api('/api/v1/profile/kyc')
}

async function save() {
  busy.value = true
  try {
    await api('/api/v1/profile', {
      method: 'PATCH',
      body: JSON.stringify({ first_name: profile.value.first_name, last_name: profile.value.last_name }),
    })
    await load()
  } finally {
    busy.value = false
  }
}

async function onAvatarFile(e: any) {
  const file = e.target.files?.[0]
  if (!file) return
  avatarErr.value = ''
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/v1/profile/avatar', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + localStorage.getItem('ob_token') },
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    avatarErr.value = body.detail || 'Upload failed'
    return
  }
  await load()
}

async function onKycFile(e: any) {
  const files = Array.from(e.target.files || [])
  kycErr.value = ''
  for (const f of files) {
    const form = new FormData()
    form.append('file', f)
    const res = await fetch('/api/v1/profile/kyc', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + localStorage.getItem('ob_token') },
      body: form,
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      kycErr.value = body.detail || `Upload failed for ${f.name}`
    }
  }
  docs.value = await api('/api/v1/profile/kyc')
}

async function submitKyc() {
  if (!docs.value.length) {
    kycErr.value = 'Upload at least one document first'
    return
  }
  kycErr.value = ''
  try {
    const res = await api('/api/v1/profile/kyc/submit', { method: 'POST', body: '{}' })
    profile.value.kyc_status = res.kyc_status
    kycResult.value = 'Documents submitted. The compliance team reviews them within one business day.'
  } catch (e: any) {
    kycErr.value = e.message
  }
}

async function applyPromo() {
  try {
    const res = await api('/api/v1/profile/promo', {
      method: 'POST',
      body: JSON.stringify({ code: promo.value }),
    })
    promoResult.value = { ok: true, text: `+${res.amount} ${res.currency} credited` }
  } catch (e: any) {
    promoResult.value = { ok: false, text: e.message }
  }
}

async function sendPhoneCode() {
  phoneErr.value = ''
  try {
    await api('/api/v1/profile/phone/change-request', {
      method: 'POST',
      body: JSON.stringify({ new_phone: newPhone.value, phone: profile.value.phone }),
    })
    phoneSent.value = true
  } catch (e: any) {
    phoneErr.value = e.message
  }
}

async function confirmPhone() {
  phoneErr.value = ''
  try {
    await api('/api/v1/profile/phone/confirm', {
      method: 'POST',
      body: JSON.stringify({ new_phone: newPhone.value, code: phoneCode.value }),
    })
    phoneOpen.value = false
    phoneSent.value = false
    phoneCode.value = ''
    await load()
  } catch (e: any) {
    phoneErr.value = e.message
  }
}

onMounted(load)
</script>

<style scoped>
.avatar {
  width: 56px; height: 56px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 18px; flex-shrink: 0;
}
.upload-label { cursor: pointer; display: inline-flex; margin-top: 4px; }
.dropzone {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  border: 1px dashed var(--line); border-radius: 12px; padding: 26px; cursor: pointer;
  transition: border-color .15s ease, background .15s ease;
}
.dropzone:hover { border-color: var(--ink); background: var(--bg); }
.dz-title { font-weight: 600; margin-bottom: 2px; }
.okmsg { color: #1E7A2E; margin-top: 10px; font-size: 13px; }
.errmsg { color: var(--red); margin-top: 10px; font-size: 13px; }
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(20, 22, 27, 0.45);
  display: flex; align-items: center; justify-content: center; z-index: 40;
}
.dialog { width: 420px; max-width: 92vw; }
</style>
