import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';
import App from '../App';

type Route = (body: any) => { status?: number; json?: unknown };
let routes: Record<string, Route> = {};
const user = (role: string, permissions: string[]) => ({ id: '1', name: 'Test User', email: 't@x.in', role, language: 'en', permissions, totp_enabled: false, idle_minutes: 30 });
const config = { product_name: 'VakeelSevak', languages: ['en', 'ml'], default_language: 'en', roles: [] };

beforeEach(() => {
  sessionStorage.clear();
  routes = {
    '/api/config': () => ({ json: config }),
    '/api/today': () => ({ json: { date: '2026-11-07', hearings_today: [], week: [], tasks: [], alerts: [] } }),
    '/api/users': () => ({ json: { items: [] } }),
  };
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const key = url.split('?')[0];
    const handler = routes[key];
    if (!handler) return new Response('{}', { status: 404 });
    const r = handler(init?.body ? JSON.parse(String(init.body)) : undefined);
    return new Response(r.status === 204 ? null : JSON.stringify(r.json ?? {}), { status: r.status ?? 200 });
  }));
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); window.history.replaceState({}, '', '/'); });

async function signIn(email = 'a@b.in') {
  fireEvent.change(await screen.findByLabelText('Email'), { target: { value: email } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'a-long-password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
}

test('shows a clear error when sign-in fails', async () => {
  routes['/api/auth/login'] = () => ({ status: 401, json: { detail: 'Email or password is not correct' } });
  render(<App />);
  await signIn();
  expect((await screen.findByRole('alert')).textContent).toContain('not correct');
});

test('asks for the authenticator code when required', async () => {
  let call = 0;
  routes['/api/auth/login'] = (b) => {
    call += 1;
    return call === 1 ? { json: { mfa_required: true } } : { json: { access_token: 't', mfa_enrollment_required: false, user: user('director', ['audit.read']) } };
  };
  routes['/api/auth/me'] = () => ({ json: { ...user('director', ['audit.read']), mfa_enrollment_required: false } });
  render(<App />);
  await signIn();
  fireEvent.change(await screen.findByLabelText(/Code from your authenticator/), { target: { value: '123456' } });
  fireEvent.click(screen.getByRole('button', { name: 'Verify and sign in' }));
  expect(await screen.findByText(/Good day, Test User/)).toBeTruthy();
});

test('menu only shows what the role can open', async () => {
  routes['/api/auth/login'] = () => ({ json: { access_token: 't', mfa_enrollment_required: false, user: user('clerk', ['cases.read_assigned']) } });
  render(<App />);
  await signIn();
  await screen.findByText(/Good day/);
  expect(screen.getByRole('button', { name: 'Cases' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Team and access' })).toBeNull();
});

test('director sees the audit log', async () => {
  routes['/api/auth/login'] = () => ({ json: { access_token: 't', mfa_enrollment_required: false, user: user('director', ['audit.read', 'cases.read_all']) } });
  routes['/api/audit'] = () => ({ json: { total: 1, items: [{ id: 'a', at: '2026-11-07T10:00:00Z', user_name: 'Adv. K. Menon', action: 'auth.login', entity_type: null, case_id: null }] } });
  render(<App />);
  await signIn();
  fireEvent.click(await screen.findByRole('button', { name: 'Team and access' }));
  fireEvent.click(await screen.findByRole('tab', { name: 'Audit log' }));
  expect(await screen.findByText('auth.login')).toBeTruthy();
  expect(screen.getByText(/cannot be edited or deleted/)).toBeTruthy();
});

test('signs out after 30 minutes without activity', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  routes['/api/auth/login'] = () => ({ json: { access_token: 't', mfa_enrollment_required: false, user: user('clerk', []) } });
  routes['/api/auth/logout'] = () => ({ status: 204 });
  render(<App />);
  await signIn();
  await screen.findByText(/Good day/);
  await act(async () => { await vi.advanceTimersByTimeAsync(31 * 60_000); });
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('30 minutes of inactivity'));
});

test('client lands on a read-only view with no menu', async () => {
  routes['/api/auth/login'] = () => ({ json: { access_token: 't', mfa_enrollment_required: false, user: user('client', ['portal.read']) } });
  routes['/api/portal/cases'] = () => ({ json: { items: [{ id: '1', title: 'Sharma v. State of Karnataka', case_number: 'O.S. 1234/2024', stage: 'Evidence', next_hearing: null }] } });
  render(<App />);
  await signIn();
  expect(await screen.findByText('Sharma v. State of Karnataka')).toBeTruthy();
  expect(screen.queryByRole('navigation')).toBeNull();
});

test('requires two-factor set-up when the office demands it', async () => {
  routes['/api/auth/login'] = () => ({ json: { access_token: 't', mfa_enrollment_required: true, user: user('junior', []) } });
  routes['/api/auth/mfa/setup'] = () => ({ json: { secret: 'ABCDEF', otpauth_uri: 'otpauth://x' } });
  render(<App />);
  await signIn();
  expect(await screen.findByRole('heading', { name: 'Set up two-factor sign-in' })).toBeTruthy();
  expect((await screen.findByTestId('secret')).textContent).toBe('ABCDEF');
});

test('forgot password gives the same answer for any email', async () => {
  routes['/api/auth/password/forgot'] = () => ({ status: 202, json: { status: 'ok' } });
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Forgot password?' }));
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'who@ever.in' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }));
  expect(await screen.findByText(/If that email has an account/)).toBeTruthy();
});
