import { useState } from 'react';
import { api } from '../auth/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, Card, DataTable, Input, StatusTag } from '../components';
import { ErrorNote, PageHead, Select, fmtDate, useAction, useData } from '../ui';

export type CaseRow = { id: string; title: string; case_number: string; court: string; stage: string; status: string; client_id: string; next_hearing: string | null };
type Client = { id: string; name: string };

function NewCase({ onDone }: { onDone: () => void }) {
  const clients = useData<{ items: Client[] }>('/clients');
  const firm = useData<{ courts: string[] }>('/settings/firm');
  const [f, setF] = useState({ title: '', case_number: '', court: '', client_id: '', party: '' });
  const act = useAction();
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const save = () => act.run(async () => {
    await api('/cases', { body: { title: f.title, case_number: f.case_number, court: f.court, client_id: f.client_id, parties: f.party ? [{ name: f.party, role: 'opposite party' }] : [] } });
    onDone();
  });
  return (
    <Card>
      <h2>New case</h2>
      <div className="vs-grid2">
        <Input label="Case title" value={f.title} onChange={set('title')} />
        <Input label="Case number" value={f.case_number} onChange={set('case_number')} />
        <Select label="Court" value={f.court} onChange={set('court')}><option value="">Choose…</option>{firm.data?.courts.map((c) => <option key={c}>{c}</option>)}</Select>
        <Select label="Client" value={f.client_id} onChange={set('client_id')}><option value="">Choose…</option>{clients.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
        <Input label="Opposite party (optional)" value={f.party} onChange={set('party')} />
      </div>
      <ErrorNote message={act.error} />
      <div className="vs-row"><Button disabled={act.busy || !f.title || !f.case_number || !f.court || !f.client_id} onClick={() => void save()}>Create case</Button><Button kind="text" onClick={onDone}>Cancel</Button></div>
    </Card>
  );
}

export function CasesPage({ onOpen, onImport }: { onOpen: (id: string) => void; onImport: () => void }) {
  const { can } = useAuth();
  const [q, setQ] = useState('');
  const [stage, setStage] = useState('');
  const [adding, setAdding] = useState(false);
  const qs = `?${new URLSearchParams({ ...(q ? { q } : {}), ...(stage ? { stage } : {}) }).toString()}`;
  const { data, reload } = useData<{ total: number; items: CaseRow[] }>(`/cases${qs}`);
  return (
    <>
      <PageHead title="Cases" help={data ? `${data.total} ${data.total === 1 ? 'case' : 'cases'} you can open` : undefined}
        actions={can('cases.write') ? <><Button kind="secondary" onClick={onImport}>Import from Excel</Button><Button onClick={() => setAdding(true)}>New case</Button></> : undefined} />
      {adding && <NewCase onDone={() => { setAdding(false); reload(); }} />}
      <div className="vs-row">
        <Input label="Search" placeholder="Title, number, party or client" value={q} onChange={(e) => setQ(e.target.value)} />
        <Input label="Stage" value={stage} onChange={(e) => setStage(e.target.value)} />
      </div>
      {data && (
        <DataTable rows={data.items} rowKey={(r) => r.id} columns={[
          { header: 'Case', cell: (r) => <><button className="vs-link" onClick={() => onOpen(r.id)}>{r.title}</button><div className="vs-help">{r.case_number}</div></> },
          { header: 'Stage', cell: (r) => <StatusTag>{r.stage}</StatusTag> },
          { header: 'Next date', cell: (r) => fmtDate(r.next_hearing) },
        ]} />
      )}
    </>
  );
}
