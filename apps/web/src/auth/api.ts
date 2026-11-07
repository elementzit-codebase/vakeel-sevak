export type User = {
  id: string; name: string; email: string; role: string; language: string;
  permissions: string[]; totp_enabled: boolean; idle_minutes: number;
};
export type LoginResult =
  | { mfa_required: true }
  | { access_token: string; mfa_enrollment_required: boolean; user: User };

let token: string | null = sessionStorage.getItem('vs_token');
let onExpired: (reason: string) => void = () => {};

export const setToken = (t: string | null) => {
  token = t;
  if (t) sessionStorage.setItem('vs_token', t); else sessionStorage.removeItem('vs_token');
};
export const getToken = () => token;
export const setOnExpired = (fn: (reason: string) => void) => { onExpired = fn; };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: opts.method ?? (opts.body ? 'POST' : 'GET'),
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof data.detail === 'string' ? data.detail : 'Something went wrong';
    if (res.status === 401 && token && !path.startsWith('/auth/login')) { setToken(null); onExpired(msg); }
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export const login = (email: string, password: string, otp?: string) =>
  api<LoginResult>('/auth/login', { body: { email, password, otp: otp || undefined, client: 'web' } });

/** Multipart upload (documents, audio, import files). The browser sets the boundary, so no JSON header. */
export async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api${path}`, { method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, typeof data.detail === 'string' ? data.detail : 'Upload failed');
  return data as T;
}

/** Authenticated download, saved through a temporary link. */
export async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(`/api${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new ApiError(res.status, 'Could not download');
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
