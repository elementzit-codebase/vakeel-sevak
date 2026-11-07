import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';
import { AuthProvider } from '../auth/AuthProvider';
import { setToken } from '../auth/api';
import { PublicStatus } from './PublicStatus';
import { CaseWorkspace } from './CaseWorkspace';

type R = (body: any) => { status?: number; json?: unknown };
let routes: Record<string, R> = {};
const calls: string[] = [];
const me = (perms: string[]) => ({ id: '1', name: 'Adv', email: 'a@x.in', role: 'advocate', language: 'en', permissions: perms, totp_enabled: false, idle_minutes: 30, mfa_enrollment_required: false });

beforeEach(() => {
  calls.length = 0;
  setToken('t');
  routes = {};
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const key = url.split('?')[0];
    calls.push(`${init?.method ?? 'GET'} ${key}`);
    const h = routes[key];
    if (!h) return new Response('{}', { status: 404 });
    const r = h(init?.body && typeof init.body === 'string' ? JSON.parse(init.body) : undefined);
    return new Response(JSON.stringify(r.json ?? {}), { status: r.status ?? 200 });
  }));
});
afterEach(() => { vi.unstubAllGlobals(); setToken(null); });

const detail = {
  id: 'c1', title: 'Sharma v. State', case_number: 'O.S. 1/2024', court: 'City Civil Court', stage: 'Evidence', status: 'open', case_type: null,
  bench: null, judge: null, cnr: null, stage_options: [], next_hearing: null, client: { id: 'k', name: 'Mr. Sharma', phone: null, email: null },
  parties: [], open_tasks: [], hearings: [{ id: 'h1', at: '2026-11-07T05:00:00Z', purpose: 'Cross-exam', court_room: null, status: 'scheduled' }],
};
const fin = { outcome: 'Adjourned', next_date: '2027-01-15', directions: [{ text: 'File reply', due_date: '2027-01-15' }], tasks: [], notes: '' };

function mount(perms: string[]) {
  routes['/api/auth/me'] = () => ({ json: me(perms) });
  routes['/api/cases/c1'] = () => ({ json: detail });
  return render(<AuthProvider><CaseWorkspace id="c1" onBack={() => {}} /></AuthProvider>);
}

test('a junior can draft a hearing record but cannot approve it', async () => {
  routes['/api/hearings/h1/records'] = () => ({ json: { items: [{ id: 'r1', status: 'draft', transcript: 'said', draft: fin, final: fin, source: 'text' }] } });
  mount(['cases.read_assigned', 'records.write', 'calendar.write', 'tasks.read']);
  fireEvent.click(await screen.findByRole('tab', { name: 'Hearings' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Record' }));
  expect(await screen.findByDisplayValue('File reply')).toBeTruthy();
  expect(screen.getByText('Draft')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Approve and save' })).toBeNull();
  expect(screen.getByText(/advocate must approve/)).toBeTruthy();
});

test('an advocate approves after editing, and the edit is saved first', async () => {
  routes['/api/hearings/h1/records'] = () => ({ json: { items: [{ id: 'r1', status: 'draft', transcript: null, draft: fin, final: fin, source: 'voice' }] } });
  routes['/api/records/r1'] = () => ({ json: {} });
  routes['/api/records/r1/approve'] = () => ({ json: {} });
  mount(['cases.read_assigned', 'records.write', 'records.approve', 'calendar.write']);
  fireEvent.click(await screen.findByRole('tab', { name: 'Hearings' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Record' }));
  fireEvent.change(await screen.findByDisplayValue('File reply'), { target: { value: 'File reply in 7 days' } });
  fireEvent.click(screen.getByRole('button', { name: 'Approve and save' }));
  await vi.waitFor(() => expect(calls.filter((c) => c.includes('/records/r1'))).toEqual(['PATCH /api/records/r1', 'POST /api/records/r1/approve']));
});

test('client tab is hidden from roles that cannot write records', async () => {
  mount(['cases.read_assigned', 'tasks.read']);
  await screen.findByRole('tab', { name: 'Overview' });
  expect(screen.queryByRole('tab', { name: 'Client' })).toBeNull();
  expect(screen.queryByRole('tab', { name: 'Documents' })).toBeNull();
});

test('public status page shows only stage and next date, and a clear message for a bad link', async () => {
  routes['/api/public/status/good'] = () => ({ json: { title: 'Sharma v. State', case_number: 'O.S. 1/2024', court: 'City Civil Court', stage: 'Evidence', next_hearing: null, office: 'Menon and Associates' } });
  const { unmount } = render(<PublicStatus token="good" />);
  expect(await screen.findByText('Sharma v. State')).toBeTruthy();
  expect(screen.getByText(/not fixed yet/)).toBeTruthy();
  unmount();
  render(<PublicStatus token="bad" />);
  expect(await screen.findByText('This link is not valid')).toBeTruthy();
});
