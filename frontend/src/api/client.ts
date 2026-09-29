/** 统一请求封装：拼后端地址、带当前服务单位头、抛网络错误、给页脚留一句可读的说明。 */
import { useSessionStore } from '@/stores/session'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

function buildHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers)
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  // 履约可见范围按当前值班单位收窄；共用只读、跨单位拦截都由后端据此判定。
  const session = useSessionStore()
  headers.set('X-Service-Unit', session.serviceUnit)
  return headers
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, { ...init, headers: buildHeaders(init) }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init)
  if (!response.ok) {
    // 优先用后端 detail（跨单位拦截原因都在里面），再退回状态码提示。
    let detail = `接口返回 ${response.status}，数据未更新`
    try {
      const body = await response.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      /* 非 JSON 错误体时保留默认提示 */
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

/** 动作类接口后端用 200 + ok=false 表达业务拦截，统一取 message。 */
export async function postAction(
  path: string,
  values: Record<string, unknown>,
): Promise<{ ok: boolean; message: string; entry: Record<string, unknown> | null }> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  if (!response.ok) {
    let detail = `接口返回 ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      /* ignore */
    }
    return { ok: false, message: detail, entry: null }
  }
  return response.json()
}
