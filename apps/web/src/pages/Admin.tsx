import { useEffect, useState } from 'react';
import { api } from '../auth/api';
import { AIDraft, Button, Card, DataTable, Input, StatusTag } from '../components';
import { ErrorNote, Select, Textarea, useAction, useData } from '../ui';

type U = { id: string; name: string; email: string; role: string; is_active: boolean; language: string };
const ROLE_LIST = ['director', 'advocate', 'junior', 'clerk', 'accountant', 'helper'];

export function Users() {
  const { data, reload } = useData<{ items: U[] }>('/users');
  const [f, setF] = useState({ name: '', email: '', role: 'junior', language: 'en' });
  const act = useAction();
  const [note, setNote] = useState<string | null>(null);
  return (
    <div className="vs-stack">
      <Card>
        <h2>Add a person</h2>
        <p className="vs-help">They receive an email to set their own password. You never see it.</p>
        <div className="vs-grid2">
          <Input label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <Input label="Email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          <Select label="Role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLE_LIST.map((r) => <option key={r}>{r}</option>)}</Select>
          <Select label="Language" value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })}><option value="en">English</option><option value="ml">മലയാളം</option></Select>
        </div>
        <ErrorNote message={act.error} />
        <Button disabled={!f.name || !f.email || act.busy} onClick={() => void act.run(async () => { await api('/users', { body: f }); setNote(`Invitation sent to ${f.email}`); setF({ ...f, name: '', email: '' }); reload(); })}>Send invitation</Button>
        {note && <StatusTag tone="ok">{note}</StatusTag>}
      </Card>
      {data && <DataTable rows={data.items.filter((u) => u.role !== 'client')} rowKey={(r) => r.id} columns={[
        { header: 'Person', cell: (r) => <>{r.name}<div className="vs-help">{r.email}</div></> },
        { header: 'Role', cell: (r) => (
          <select aria-label={`Role for ${r.name}`} className="vs-input" value={r.role} onChange={(e) => void act.run(async () => { await api(`/users/${r.id}`, { method: 'PATCH', body: { role: e.target.value } }); reload(); })}>
            {ROLE_LIST.map((x) => <option key={x}>{x}</option>)}
          </select>) },
        { header: 'Status', cell: (r) => r.is_active ? <StatusTag tone="ok">Active</StatusTag> : <StatusTag>Deactivated</StatusTag> },
        { header: '', cell: (r) => <Button kind="secondary" onClick={() => void act.run(async () => { await api(`/users/${r.id}`, { method: 'PATCH', body: { is_active: !r.is_active } }); reload(); })}>{r.is_active ? 'Deactivate' : 'Reactivate'}</Button> },
      ]} />}
    </div>
  );
}

type Firm = { courts: string[]; reminder_offsets: number[]; quiet_hours: { start: string; end: string }; client_comms: { enabled: boolean; channels: string[] }; inactive_days: number; stage_templates: Record<string, string[]> };
export function FirmSettings() {
  const { data, reload } = useData<Firm>('/settings/firm');
  const [f, setF] = useState<Firm | null>(null);
  const [saved, setSaved] = useState(false);
  const act = useAction();
  useEffect(() => { if (data) setF(data); }, [data]);
  if (!f) return null;
  const ch = (c: string) => setF({ ...f, client_comms: { ...f.client_comms, channels: f.client_comms.channels.includes(c) ? f.client_comms.channels.filter((x) => x !== c) : [...f.client_comms.channels, c] } });
  return (
    <div className="vs-stack">
      <Card>
        <h2>Messages to clients</h2>
        <p>Off for everyone until you turn it on. While off, no reminder, message, status link or chat reaches a client.</p>
        <label className="vs-check"><input type="checkbox" checked={f.client_comms.enabled} onChange={(e) => setF({ ...f, client_comms: { ...f.client_comms, enabled: e.target.checked } })} /> Allow messages and access for clients</label>
        <div className="vs-row">{['email', 'push', 'whatsapp'].map((c) => <label key={c} className="vs-check"><input type="checkbox" checked={f.client_comms.channels.includes(c)} onChange={() => ch(c)} /> {c}</label>)}</div>
      </Card>
      <Card>
        <h2>Reminders</h2>
        <Input label="Days before a hearing (comma separated; 0 is the day itself)" value={f.reminder_offsets.join(', ')} onChange={(e) => setF({ ...f, reminder_offsets: e.target.value.split(',').map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x) && x >= 0) })} />
        <div className="vs-row">
          <Input label="Quiet from" type="time" value={f.quiet_hours.start} onChange={(e) => setF({ ...f, quiet_hours: { ...f.quiet_hours, start: e.target.value } })} />
          <Input label="Quiet until" type="time" value={f.quiet_hours.end} onChange={(e) => setF({ ...f, quiet_hours: { ...f.quiet_hours, end: e.target.value } })} />
        </div>
        <Input label="Flag a case with no activity after (days)" type="number" value={f.inactive_days} onChange={(e) => setF({ ...f, inactive_days: Number(e.target.value) })} />
      </Card>
      <Card>
        <h2>Courts</h2>
        <Textarea label="One court per line" value={f.courts.join('\n')} onChange={(e) => setF({ ...f, courts: e.target.value.split('\n').map((x) => x.trim()).filter(Boolean) })} />
        <h2>Stage templates</h2>
        {Object.entries(f.stage_templates).map(([k, v]) => (
          <Input key={k} label={`${k} (stages, comma separated)`} value={v.join(', ')} onChange={(e) => setF({ ...f, stage_templates: { ...f.stage_templates, [k]: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) } })} />
        ))}
      </Card>
      <ErrorNote message={act.error} />
      <div className="vs-row"><Button disabled={act.busy} onClick={() => void act.run(async () => { await api('/settings/firm', { method: 'PUT', body: f }); setSaved(true); reload(); })}>Save settings</Button>{saved && <StatusTag tone="ok">Saved</StatusTag>}</div>
    </div>
  );
}

type Daily = { day: string; items: { user: string; action: string; case: string; count: number }[]; summary: { body: string; status: string } | null };
export function DailyLog() {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const { data, reload } = useData<Daily>(`/daily/${day}`);
  const act = useAction();
  return (
    <div className="vs-stack">
      <Input label="Day" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
      <p className="vs-help">Built from the audit log. It lists who did what and on which case, never what the case contains.</p>
      {data && <DataTable rows={data.items} rowKey={(r) => `${r.user}${r.action}${r.case}`} columns={[
        { header: 'Person', cell: (r) => r.user }, { header: 'Action', cell: (r) => <StatusTag>{r.action}</StatusTag> },
        { header: 'Case', cell: (r) => r.case || '—' }, { header: 'Times', cell: (r) => r.count }]} />}
      <Button kind="secondary" disabled={act.busy} onClick={() => void act.run(async () => { await api(`/daily/${day}/summary`, { body: {} }); reload(); })}>Write AI summary</Button>
      <ErrorNote message={act.error} />
      {data?.summary && (
        <AIDraft title="Day summary" approved={data.summary.status === 'approved'}
          actions={data.summary.status !== 'approved' ? <Button onClick={() => void act.run(async () => { await api(`/daily/${day}/approve`, { body: {} }); reload(); })}>Approve</Button> : undefined}>
          <p style={{ whiteSpace: 'pre-wrap' }}>{data.summary.body}</p>
        </AIDraft>
      )}
    </div>
  );
}
