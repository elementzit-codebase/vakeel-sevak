import { useState } from 'react';
import { api } from '../auth/api';
import { useAuth } from '../auth/AuthProvider';
import { AIDraft, Button, Card, Input, StatusTag } from '../components';
import { Empty, ErrorNote, PageHead, Select, Textarea, fmtDate, inr, useAction, useData } from '../ui';

type Sec = { id: string; act: string; number: string; title: string; text: string | null; verified: boolean; warning: string | null };
type Map = { old: string; new: string; note: string | null; verified: boolean; warning: string | null };

export function StatutesPage() {
  const [q, setQ] = useState('');
  const [mapAct, setMapAct] = useState('IPC');
  const [mapNo, setMapNo] = useState('');
  const [secs, setSecs] = useState<Sec[] | null>(null);
  const [maps, setMaps] = useState<Map[] | null>(null);
  const act = useAction();
  return (
    <>
      <PageHead title="BNS, BNSS and BSA" help="Search sections and find the new number for an old IPC, CrPC or Evidence Act section." />
      <Card>
        <h2>Search</h2>
        <div className="vs-row"><Input label="Section number or words" value={q} onChange={(e) => setQ(e.target.value)} />
          <Button disabled={!q || act.busy} onClick={() => void act.run(async () => setSecs((await api<{ items: Sec[] }>(`/statutes/search?q=${encodeURIComponent(q)}`)).items))}>Search</Button></div>
        {secs && (secs.length === 0 ? <p className="vs-help">No match. The library only holds sections your office has loaded.</p> : (
          <ul className="vs-list">{secs.map((s) => <li key={s.id}><span><strong>{s.act} {s.number}</strong> {s.title}{s.text && <p>{s.text}</p>}{s.warning && <div className="vs-help">{s.warning}</div>}</span>{s.verified ? <StatusTag tone="ok">Verified</StatusTag> : <StatusTag tone="caution">Unverified</StatusTag>}</li>)}</ul>
        ))}
      </Card>
      <Card>
        <h2>Old to new (and back)</h2>
        <div className="vs-row">
          <Select label="Act" value={mapAct} onChange={(e) => setMapAct(e.target.value)}>{['IPC', 'CRPC', 'IEA', 'BNS', 'BNSS', 'BSA'].map((a) => <option key={a}>{a}</option>)}</Select>
          <Input label="Section" value={mapNo} onChange={(e) => setMapNo(e.target.value)} />
          <Button disabled={!mapNo || act.busy} onClick={() => void act.run(async () => setMaps((await api<{ items: Map[] }>(`/statutes/map?act=${mapAct}&number=${encodeURIComponent(mapNo)}`)).items))}>Find</Button>
        </div>
        {maps && (maps.length === 0 ? <p className="vs-help">No mapping loaded for that section.</p> : (
          <ul className="vs-list">{maps.map((m, i) => <li key={i}><span><strong>{m.old}</strong> → <strong>{m.new}</strong>{m.note && <div className="vs-help">{m.note}</div>}{m.warning && <div className="vs-help">{m.warning}</div>}</span>{m.verified ? <StatusTag tone="ok">Verified</StatusTag> : <StatusTag tone="caution">Unverified</StatusTag>}</li>)}</ul>
        ))}
      </Card>
      <ErrorNote message={act.error} />
    </>
  );
}

type Cons = { id: string; status: string; raw_notes: string; structured: { facts: string[]; issues: string[]; parties: string[]; dates: { date: string; what: string }[]; documents_needed: string[]; next_steps: string[] } };
export function ConsultPage() {
  const { data, reload } = useData<{ items: Cons[] }>('/consultations');
  const clients = useData<{ items: { id: string; name: string }[] }>('/clients');
  const [notes, setNotes] = useState('');
  const [clientId, setClientId] = useState('');
  const act = useAction();
  return (
    <>
      <PageHead title="Consultations" help="Type or dictate rough notes. AI organises them; you check and confirm." />
      <Card>
        <Textarea label="Notes from the meeting" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <Select label="Client (optional)" value={clientId} onChange={(e) => setClientId(e.target.value)}><option value="">Not yet a client</option>{clients.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
        <ErrorNote message={act.error} />
        <Button disabled={!notes.trim() || act.busy} onClick={() => void act.run(async () => { await api('/consultations', { body: { raw_notes: notes, client_id: clientId || null } }); setNotes(''); reload(); })}>Structure with AI</Button>
      </Card>
      {data?.items.length === 0 && <Empty>No consultations yet.</Empty>}
      {data?.items.map((c) => (
        <AIDraft key={c.id} title="Consultation" approved={c.status === 'confirmed'}
          actions={c.status === 'draft' ? <Button onClick={() => void act.run(async () => { await api(`/consultations/${c.id}/confirm`, { body: {} }); reload(); })}>Confirm</Button> : undefined}>
          {(['facts', 'issues', 'parties', 'documents_needed', 'next_steps'] as const).map((k) => c.structured[k]?.length > 0 && (
            <div key={k}><strong>{k.replace('_', ' ')}</strong><ul>{c.structured[k].map((x, i) => <li key={i}>{x}</li>)}</ul></div>
          ))}
          {c.structured.dates?.length > 0 && <div><strong>dates</strong><ul>{c.structured.dates.map((d, i) => <li key={i}>{d.date}: {d.what}</li>)}</ul></div>}
        </AIDraft>
      ))}
    </>
  );
}

export function FeesPage({ onOpenClient }: { onOpenClient: (id: string) => void }) {
  const { data } = useData<{ total_due_paise: number; items: { client_id: string; client: string; billed_paise: number; received_paise: number; due_paise: number }[] }>('/fees/summary');
  if (!data) return null;
  return (
    <>
      <PageHead title="Fees" help={`Total due ${inr(data.total_due_paise)}. Manual ledger: payments are recorded here, not collected.`} />
      {data.items.length === 0 ? <Empty>No fee entries yet. Open a client to add one.</Empty> : (
        <Card><ul className="vs-list">{data.items.map((r) => (
          <li key={r.client_id}><button className="vs-link" onClick={() => onOpenClient(r.client_id)}>{r.client}</button>
            <span>Billed {inr(r.billed_paise)} · Received {inr(r.received_paise)} · {r.due_paise > 0 ? <StatusTag tone="alert">Due {inr(r.due_paise)}</StatusTag> : <StatusTag tone="ok">Settled</StatusTag>}</span></li>
        ))}</ul></Card>
      )}
    </>
  );
}

export function AskPage() {
  const [q, setQ] = useState('');
  const [res, setRes] = useState<{ answer: string; sources: { type: string; id: string }[] } | null>(null);
  const hist = useData<{ items: { id: string; question: string; at: string }[] }>('/ask/history');
  const act = useAction();
  return (
    <>
      <PageHead title="Ask" help="Ask about your own cases, hearings and tasks. It only sees what you are allowed to open." />
      <div className="vs-row"><Input label="Your question" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button disabled={q.trim().length < 3 || act.busy} onClick={() => void act.run(async () => { setRes(await api('/ask', { body: { question: q } })); hist.reload(); })}>Ask</Button></div>
      <ErrorNote message={act.error} />
      {res && <AIDraft title="Answer"><p>{res.answer}</p><div className="vs-help">{res.sources.length} source{res.sources.length === 1 ? '' : 's'} from your cases. Check the case before relying on it.</div></AIDraft>}
      {hist.data && hist.data.items.length > 0 && <Card><h3>Recent questions</h3><ul className="vs-list">{hist.data.items.slice(0, 8).map((h) => <li key={h.id}><span>{h.question}</span><span className="vs-help">{fmtDate(h.at)}</span></li>)}</ul></Card>}
    </>
  );
}
