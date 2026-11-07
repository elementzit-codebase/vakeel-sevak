import { useState } from 'react';
import { api, download } from '../auth/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, Card, DataTable, Input, StatusTag } from '../components';
import { ErrorNote, PageHead, Select, fmtDate, inr, useAction, useData } from '../ui';

type Client = { id: string; name: string; phone: string | null; email: string | null; language: string };
type Fee = { id: string; kind: string; amount_paise: number; entry_date: string; mode: string | null; note: string | null; receipt_no: string | null };
type Ledger = { balance: { billed_paise: number; received_paise: number; due_paise: number }; items: Fee[] };

function FeeLedger({ clientId }: { clientId: string }) {
  const { can } = useAuth();
  const { data, reload } = useData<Ledger>(`/clients/${clientId}/fees`);
  const [f, setF] = useState({ kind: 'received', amount: '', date: new Date().toISOString().slice(0, 10), mode: 'upi', note: '' });
  const [notice, setNotice] = useState<string | null>(null);
  const act = useAction();
  if (!data) return null;
  const b = data.balance;
  return (
    <Card>
      <h2>Fees</h2>
      <div className="vs-grid2">
        <div><div className="vs-help">Billed</div><strong>{inr(b.billed_paise)}</strong></div>
        <div><div className="vs-help">Received</div><strong>{inr(b.received_paise)}</strong></div>
        <div><div className="vs-help">Due</div><strong>{b.due_paise > 0 ? <StatusTag tone="alert">{inr(b.due_paise)}</StatusTag> : inr(b.due_paise)}</strong></div>
      </div>
      <DataTable rows={data.items} rowKey={(r) => r.id} columns={[
        { header: 'Date', cell: (r) => fmtDate(r.entry_date) },
        { header: 'Entry', cell: (r) => <>{r.kind}{r.note ? <div className="vs-help">{r.note}</div> : null}</> },
        { header: 'Amount', cell: (r) => inr(r.amount_paise) },
        { header: 'Receipt', cell: (r) => r.receipt_no ? <button className="vs-link" onClick={() => void act.run(() => download(`/fees/${r.id}/receipt.pdf`, `${r.receipt_no!.replace(/\//g, '-')}.pdf`))}>{r.receipt_no}</button> : '' },
      ]} />
      {can('fees.write') && (
        <div className="vs-stack">
          <h3>Add an entry</h3>
          <div className="vs-grid2">
            <Select label="Type" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="fee">Fee billed</option><option value="expense">Expense</option><option value="received">Payment received</option></Select>
            <Input label="Amount (₹)" inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} />
            <Input label="Date" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
            <Select label="Mode" value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}><option value="cash">Cash</option><option value="upi">UPI</option><option value="cheque">Cheque</option><option value="bank">Bank transfer</option></Select>
            <Input label="Note" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
          </div>
          <div className="vs-row">
            <Button disabled={!Number(f.amount) || act.busy} onClick={() => void act.run(async () => {
              await api(`/clients/${clientId}/fees`, { body: { kind: f.kind, amount_paise: Math.round(Number(f.amount) * 100), entry_date: f.date, mode: f.mode, note: f.note || null } });
              setF({ ...f, amount: '', note: '' }); reload();
            })}>Save entry</Button>
            {b.due_paise > 0 && <Button kind="secondary" onClick={() => void act.run(async () => { const n = await api<{ body: string }>(`/clients/${clientId}/fee-notice`, { body: {} }); setNotice(n.body); })}>Draft fee notice</Button>}
          </div>
          {notice && <p className="vs-help">Notice drafted for approval by a Director or Advocate: “{notice}”</p>}
        </div>
      )}
      <ErrorNote message={act.error} />
    </Card>
  );
}

type C360 = Client & { address: string | null; cases: { id: string; title: string; case_number: string; stage: string; next_hearing: string | null }[]; balance?: unknown };

function Client360({ id, onBack, onOpenCase }: { id: string; onBack: () => void; onOpenCase: (id: string) => void }) {
  const { can } = useAuth();
  const { data } = useData<C360>(`/clients/${id}`);
  if (!data) return null;
  return (
    <>
      <Button kind="text" onClick={onBack}>← Clients</Button>
      <PageHead title={data.name} help={[data.phone, data.email].filter(Boolean).join(' · ')} />
      <Card>
        <h2>Cases</h2>
        {data.cases.length === 0 ? <p className="vs-help">No cases you can open.</p> : (
          <ul className="vs-list">{data.cases.map((c) => <li key={c.id}><span><button className="vs-link" onClick={() => onOpenCase(c.id)}>{c.title}</button><div className="vs-help">{c.case_number}</div></span><span>{c.stage} · next {fmtDate(c.next_hearing)}</span></li>)}</ul>
        )}
      </Card>
      {can('fees.read') && <FeeLedger clientId={id} />}
    </>
  );
}

export function ClientsPage({ onOpenCase }: { onOpenCase: (id: string) => void }) {
  const { can } = useAuth();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ name: '', phone: '', email: '', language: 'en' });
  const { data, reload } = useData<{ items: Client[] }>(`/clients${q ? `?q=${encodeURIComponent(q)}` : ''}`);
  const act = useAction();
  if (sel) return <Client360 id={sel} onBack={() => setSel(null)} onOpenCase={onOpenCase} />;
  return (
    <>
      <PageHead title="Clients" actions={can('clients.write') ? <Button onClick={() => setAdding(true)}>New client</Button> : undefined} />
      {adding && (
        <Card>
          <div className="vs-grid2">
            <Input label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
            <Input label="Phone" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
            <Input label="Email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
            <Select label="Language" value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })}><option value="en">English</option><option value="ml">മലയാളം</option></Select>
          </div>
          <ErrorNote message={act.error} />
          <div className="vs-row"><Button disabled={!f.name || act.busy} onClick={() => void act.run(async () => { await api('/clients', { body: { ...f, phone: f.phone || null, email: f.email || null } }); setAdding(false); setF({ name: '', phone: '', email: '', language: 'en' }); reload(); })}>Save client</Button><Button kind="text" onClick={() => setAdding(false)}>Cancel</Button></div>
        </Card>
      )}
      <Input label="Search clients" value={q} onChange={(e) => setQ(e.target.value)} />
      {data && <DataTable rows={data.items} rowKey={(r) => r.id} columns={[
        { header: 'Client', cell: (r) => <button className="vs-link" onClick={() => setSel(r.id)}>{r.name}</button> },
        { header: 'Phone', cell: (r) => r.phone ?? '—' },
        { header: 'Language', cell: (r) => r.language },
      ]} />}
    </>
  );
}
