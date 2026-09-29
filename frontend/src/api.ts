export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

const TOKEN_KEY = 'ob_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export async function api(path: string, opts: any = {}): Promise<any> {
  const headers: Record<string, string> = Object.assign(
    { 'Content-Type': 'application/json' },
    opts.headers || {}
  )
  const token = getToken()
  if (token) headers['Authorization'] = 'Bearer ' + token
  const res = await fetch(path, { ...opts, headers, credentials: 'include' })
  let data: any = {}
  try {
    data = await res.json()
  } catch {
    data = {}
  }
  if (!res.ok) throw new ApiError(data.detail || data.error || res.statusText, res.status)
  return data
}

export function fmtMoney(value: number, currency: string): string {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value) + ' ' + currency
}
