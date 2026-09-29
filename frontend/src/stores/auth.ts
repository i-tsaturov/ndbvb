import { defineStore } from 'pinia'
import { api, setToken, clearToken, getToken } from '../api'

export const useAuth = defineStore('auth', {
  state: () => ({
    user: null as any,
    challengeId: '' as string,
    token: getToken() as string | null,
  }),
  getters: {
    authenticated: (s) => !!s.token,
    isBackoffice: (s) => !!(s.user && s.user.is_backoffice),
  },
  actions: {
    async login(login: string, password: string) {
      const res = await api('/api/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({ login, password }),
      })
      this.challengeId = res.challenge_id
      return res
    },
    async verify(challengeId: string, code: string) {
      const res = await api('/api/v1/auth/verify-otp', {
        method: 'POST',
        body: JSON.stringify({ challenge_id: challengeId, code }),
      })
      setToken(res.token)
      this.token = res.token
      this.user = res.user
      return res
    },
    async logout() {
      clearToken()
      this.token = null
      this.user = null
      this.challengeId = ''
    },
  },
})
