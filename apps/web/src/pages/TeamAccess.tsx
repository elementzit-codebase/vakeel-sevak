import { useCallback, useEffect, useState } from 'react';
import { api } from '../auth/api';
import { Button, DataTable, Input, StatusTag } from '../components';
import { DailyLog, FirmSettings, Users } from './Admin';

type Entry = { id: string; at: string; user_name: string | null; action: string; entity_type: string | null; case_id: string | null };
const ROLES = ['advocate', 'junior', 'clerk', 'accountant', 'helper', 'client', 'director'];

function AuditLog() {
  const [action, setAction] = useState('');
  const [data, setData] = useState<{ total: number; items: Entry[] } | null>(null);
  const load = useCallback(() => {
    const q = action ? `?action=${encodeURIComponent(action)}` : '';
    api<{ total: number; items: Entry[] }>(`/audit${q}`).then(setData);
  }, [action]);
  useEffect(load, [load]);
  return (
    <section aria-label="Audit log" className="vs-stack">
      <div className="vs-row">
        <Input label="Filter by action" placeholder="auth.*  or  case.view" value={action} onChange={(e) => setAction(e.target.value)} />
        <Button kind="secondary" onClick={load}>Apply</Button>
      </div>
      {data && (
        <>
          <div className="vs-help">{data.total} entries. The log cannot be edited or deleted.</div>
          <DataTable rows={data.items} rowKey={(r) => r.id} columns={[
            { header: 'Time', cell: (r) => new Date(r.at).toLocaleString('en-IN') },
            { header: 'User', cell: (r) => r.user_name ?? 'Unknown' },
            { header: 'Action', cell: (r) => <StatusTag>{r.action}</StatusTag> },
          ]} />
        </>
      )}
    </section>
  );
}

function Security() {
  const [roles, setRoles] = useState<string[] | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { api<{ mfa_roles: string[] }>('/settings/security').then((r) => setRoles(r.mfa_roles)); }, []);
  if (!roles) return null;
  const toggle = (r: string) => { setSaved(false); setRoles(roles.includes(r) ? roles.filter((x) => x !== r) : [...roles, r]); };
  return (
    <section aria-label="Security" className="vs-stack">
      <p>Two-factor sign-in is off for everyone until you turn it on. Choose the roles that must use it.</p>
      <fieldset className="vs-row">
        <legend className="vs-help">Require two-factor for</legend>
        {ROLES.map((r) => (
          <label key={r} className="vs-check"><input type="checkbox" checked={roles.includes(r)} onChange={() => toggle(r)} /> {r}</label>
        ))}
      </fieldset>
      <div className="vs-row">
        <Button onClick={() => api('/settings/security/mfa-roles', { method: 'PUT', body: { roles } }).then(() => setSaved(true))}>Save</Button>
        {saved && <StatusTag tone="ok">Saved</StatusTag>}
      </div>
    </section>
  );
}

export function TeamAccess() {
  const [tab, setTab] = useState<'users' | 'firm' | 'audit' | 'security' | 'daily'>('users');
  const tabs = [['users', 'People'], ['firm', 'Firm settings'], ['audit', 'Audit log'], ['security', 'Security'], ['daily', 'Daily log']] as const;
  return (
    <>
      <h1>Team and access</h1>
      <div className="vs-tabs" role="tablist">
        {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === 'users' && <Users />}
      {tab === 'firm' && <FirmSettings />}
      {tab === 'audit' && <AuditLog />}
      {tab === 'security' && <Security />}
      {tab === 'daily' && <DailyLog />}
    </>
  );
}
