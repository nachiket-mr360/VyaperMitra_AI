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

  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    throw new ApiClientError('The server returned an unexpected response.', res.status, 'invalid_json')
  }

  if (!res.ok) {
    const err = body as ApiErrorBody | null
    throw new ApiClientError(
      err?.error?.message ?? `Request failed (${res.status})`,
      res.status,
      err?.error?.code ?? 'http_error',
    )
  }

  return body as T
}
