<template>
  <div class="login-wrap">
    <div class="login-card card">
      <div class="brand"><span class="mark"></span> OnlineBank</div>
      <h1>Welcome back</h1>
      <p class="muted" style="margin-bottom:18px">
        Demo account: <span class="mono">ama@onlinebank.app</span> /
        <span class="mono">OnlineBank!123</span>
      </p>

      <template v-if="!challenge">
        <div class="field">
          <label>Email or phone number</label>
          <input class="input" v-model="login" placeholder="ama@onlinebank.app or +233501234567" @keyup.enter="doLogin" />
        </div>
        <div class="field">
          <label>Password</label>
          <input class="input" type="password" v-model="password" placeholder="OnlineBank!123" @keyup.enter="doLogin" />
        </div>
        <button class="btn red" style="width:100%" :disabled="busy" @click="doLogin">
          {{ busy ? 'Signing in…' : 'Continue' }}
        </button>
      </template>

      <template v-else>
        <div class="otp-note card" style="background:#FFF5F5;border-color:#F2C1C1">
          <b>Verification code sent by SMS.</b><br />
          <span v-if="sentPhone">Delivered to <span class="mono">{{ maskPhone(sentPhone) }}</span>.<br /></span>
          Didn't get the code? Check the
          <a class="mono" :href="gwUrl" target="_blank">SMS gateway</a>.
        </div>
        <div class="field" style="margin-top:14px">
          <label>4-digit code</label>
          <input class="input mono" v-model="code" maxlength="4" placeholder="0000" @keyup.enter="doVerify" />
        </div>
        <div class="row">
          <button class="btn red" style="flex:1" :disabled="busy" @click="doVerify">
            {{ busy ? 'Verifying…' : 'Verify' }}
          </button>
          <button class="btn ghost" @click="back">Back</button>
        </div>
      </template>

      <p v-if="error" class="error">{{ error }}</p>
    </div>
    <p class="foot muted">Demo environment · support@onlinebank.app</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'

const auth = useAuth()
const router = useRouter()
const login = ref('')
const password = ref('')
const code = ref('')
const challenge = ref('')
const sentPhone = ref('')
const gwUrl = `http://${window.location.hostname}:9500`
const gwShort = `${window.location.hostname}:9500`
const busy = ref(false)
const error = ref('')

function maskPhone(p: string): string {
  if (!p || p.length < 6) return p
  return p.slice(0, 3) + '*'.repeat(p.length - 5) + p.slice(-2)
}

async function doLogin() {
  busy.value = true
  error.value = ''
  try {
    const res = await auth.login(login.value, password.value)
    challenge.value = res.challenge_id
    sentPhone.value = res.phone || ''
  } catch (e: any) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function back() {
  challenge.value = ''
  sentPhone.value = ''
  password.value = ''
}

async function doVerify() {
  busy.value = true
  error.value = ''
  try {
    await auth.verify(challenge.value, code.value)
    router.push('/')
  } catch (e: any) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 40px 20px; gap: 18px;
}
.login-card { width: 420px; max-width: 100%; }
.brand { display: flex; align-items: center; gap: 8px; font-weight: 700; margin-bottom: 18px; }
.mark { width: 22px; height: 6px; background: var(--red); border-radius: 1px; }
h1 { margin-bottom: 6px; }
.otp-note { font-size: 14px; padding: 12px 14px; border-radius: 10px; }
.error { color: var(--red); margin-top: 12px; font-size: 14px; }
.foot { font-size: 12px; }
</style>
