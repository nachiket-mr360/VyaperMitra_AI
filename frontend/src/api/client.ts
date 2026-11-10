export type ApiErrorBody = {
  ok: false
  error: { code: string; message: string }
}

export class ApiClientError extends Error {
  status: number
  code: string

  constructor(message: string, status: number, code: string) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.code = code
  }
}

function parseError(res: Response, body: unknown): ApiClientError {
  const err = body as ApiErrorBody | null
  return new ApiClientError(
    err?.error?.message ?? `Request failed (${res.status})`,
    res.status,
    err?.error?.code ?? 'http_error',
  )
}

async function parseJson(res: Response): Promise<unknown> {
  const text = await res.text()
  try {
    return text ? JSON.parse(text) : null
  } catch {
    throw new ApiClientError('The server returned an unexpected response.', res.status, 'invalid_json')
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(path)
  } catch {
    throw new ApiClientError(
      'Cannot reach the VyaparMitra server. Check that the backend is running.',
      0,
      'network_error',
    )
  }
  const body = await parseJson(res)
  if (!res.ok) {
    throw parseError(res, body)
  }
  return body as T
}

export async function apiPostJson<T>(path: string, body: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiClientError(
      'Cannot reach the VyaparMitra server. Check that the backend is running.',
      0,
      'network_error',
    )
  }
  const parsed = await parseJson(res)
  if (!res.ok) {
    throw parseError(res, parsed)
  }
  return parsed as T
}

async function jsonMethod<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiClientError(
      'Cannot reach the VyaparMitra server. Check that the backend is running.',
      0,
      'network_error',
    )
  }
  const parsed = await parseJson(res)
  if (!res.ok) {
    throw parseError(res, parsed)
  }
  return parsed as T
}

export function apiPatchJson<T>(path: string, body: unknown) {
  return jsonMethod<T>('PATCH', path, body)
}

export function apiDelete<T>(path: string) {
  return jsonMethod<T>('DELETE', path)
}

export async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, { method: 'POST', body: form })
  } catch {
    throw new ApiClientError(
      'Cannot reach the VyaparMitra server. Check that the backend is running.',
      0,
      'network_error',
    )
  }
  const body = await parseJson(res)
  if (!res.ok) {
    throw parseError(res, body)
  }
  return body as T
}
