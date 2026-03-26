const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'
const API_TIMEOUT = Number(import.meta.env.VITE_API_TIMEOUT || 60000)

function buildUrl(path) {
  if (/^https?:\/\//i.test(path)) {
    return path
  }
  if (!path.startsWith('/')) {
    return `${API_BASE_URL}/${path}`
  }
  return `${API_BASE_URL}${path}`
}

function extractErrorMessage(payload, fallback) {
  if (!payload) {
    return fallback
  }
  if (typeof payload === 'string') {
    return payload || fallback
  }
  return payload.message || payload.detail || fallback
}

export async function request(path, options = {}) {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), API_TIMEOUT)

  try {
    const response = await fetch(buildUrl(path), {
      method: options.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    })

    const contentType = response.headers.get('content-type') || ''
    const isJson = contentType.includes('application/json')
    const payload = isJson ? await response.json() : await response.text()

    if (!response.ok) {
      throw new Error(extractErrorMessage(payload, `请求失败（HTTP ${response.status}）`))
    }

    if (isJson && payload && payload.success === false) {
      throw new Error(extractErrorMessage(payload, '请求失败'))
    }

    return payload
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('请求超时，请稍后重试')
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
  }
}
