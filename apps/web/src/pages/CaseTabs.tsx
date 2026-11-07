import { useRef, useState } from 'react';
import { api, download, upload } from '../auth/api';
import { useAuth } from '../auth/AuthProvider';
import { AIDraft, Button, Card, Input, StatusTag } from '../components';
import { Confirm, Empty, ErrorNote, Select, Textarea, fmtDate, fmtTime, useAction, useData } from '../ui';

export type Detail = {
  id: string; title: string; case_number: string; court: string; stage: string; status: string; case_type: string | null;
  bench: string | null; judge: string | null; cnr: string | null; stage_options: string[];
  client: { id: string; name: string; phone: string | null; email: string | null };
  parties: { id: string; name: string; role: string }[];
  hearings: { id: string; at: string; purpose: string | null; court_room: string | null; status: string }[];
  open_tasks: { id: string; title: string; due_date: string | null }[];
  assignee_ids?: string[];
};
type Team = { items: { id: string; name: string; role: string }[] };

export function Overview({ d, reload }: { d: Detail; reload: () => void }) {
  const { can } = useAuth();
  const team = useData<Team>(can('users.manage') ? '/team' : null);
  const act = useAction();
  const [stage, setStage] = useState(d.stage);
  const [sel, setSel] = useState<string[]>(d.assignee_ids ?? []);
  return (
    <div className="vs-stack">
      <Card>
        <div className="vs-grid2">
          <div><div className="vs-help">Court</div>{d.court}</div>
          <div><div className="vs-help">Client</div>{d.client.name}<div className="vs-help">{d.client.phone}</div></div>
          <div><div className="vs-help">Judge / bench</div>{d.judge ?? '—'} {d.bench ? `· ${d.bench}` : ''}</div>
          <div><div className="vs-help">CNR</div>{d.cnr ?? '—'}</div>
        </div>
        <h3>Parties</h3>
        {d.parties.length === 0 ? <p className="vs-help">No parties recorded.</p> : <ul className="vs-list">{d.parties.map((p) => <li key={p.id}><span>{p.name}</span><StatusTag>{p.role}</StatusTag></li>)}</ul>}
      </Card>
      {can('cases.write') && (
        <Card>
          <h3>Stage</h3>
          <div className="vs-row">
            {d.stage_options.length > 0
              ? <Select label="Stage" value={stage} onChange={(e) => setStage(e.target.value)}>{[...new Set([d.stage, ...d.stage_options])].map((s) => <option key={s}>{s}</option>)}</Select>
              : <Input label="Stage" value={stage} onChange={(e) => setStage(e.target.value)} />}
            <Button disabled={stage === d.stage || act.busy} onClick={() => void act.run(async () => { await api(`/cases/${d.id}`, { method: 'PATCH', body: { stage } }); reload(); })}>Save stage</Button>
          </div>
          <ErrorNote message={act.error} />
        </Card>
      )}
      {can('users.manage') && team.data && (
        <Card>
          <h3>Who can open this case</h3>
          <p className="vs-help">The Director always can. Everyone else needs to be listed here.</p>
          <div className="vs-stack">
            {team.data.items.filter((m) => m.role !== 'director').map((m) => (
              <label key={m.id} className="vs-check">
                <input type="checkbox" checked={sel.includes(m.id)} onChange={(e) => setSel(e.target.checked ? [...sel, m.id] : sel.filter((x) => x !== m.id))} /> {m.name} <span className="vs-help">{m.role}</span>
              </label>
            ))}
          </div>
          <Button onClick={() => void act.run(async () => { await api(`/cases/${d.id}/assignments`, { method: 'PUT', body: { user_ids: sel } }); reload(); })}>Save access</Button>
        </Card>
      )}
    </div>
  );
}

type Rec = { id: string; status: string; transcript: string | null; draft: Fin; final: Fin; source: string };
type Fin = { outcome: string; next_date: string | null; directions: { text: string; due_date: string | null }[]; tasks: { text: string; due_date: string | null }[]; notes: string };

function RecordReview({ rec, onChange }: { rec: Rec; onChange: () => void }) {
  const { can } = useAuth();
  const [f, setF] = useState<Fin>(rec.final);
  const act = useAction();
  const [msg, setMsg] = useState<string | null>(null);
  const approved = rec.status === 'approved';
  const edit = (dir: number, text: string) => setF({ ...f, directions: f.directions.map((d, i) => (i === dir ? { ...d, text } : d)) });
  return (
    <AIDraft title="Hearing record" approved={approved}
      actions={!approved ? <>
        <Button kind="secondary" disabled={act.busy} onClick={() => void act.run(async () => { await api(`/records/${rec.id}`, { method: 'PATCH', body: f }); onChange(); })}>Save edits</Button>
        {can('records.approve') ? <Button disabled={act.busy} onClick={() => void act.run(async () => { await api(`/records/${rec.id}`, { method: 'PATCH', body: f }); await api(`/records/${rec.id}/approve`, { body: {} }); onChange(); })}>Approve and save</Button>
          : <span className="vs-help">An advocate must approve this.</span>}
      </> : <>
        {can('records.write') && <Button kind="secondary" onClick={() => void act.run(async () => { const m = await api<{ id: string }>(`/records/${rec.id}/client-message`, { body: {} }); setMsg(m.id); })}>Draft client message</Button>}
        {msg && <span className="vs-help">Draft created. Review it in the Messages tab.</span>}
      </>}>
      {rec.transcript && <details><summary className="vs-help">What was said ({rec.source})</summary><p>{rec.transcript}</p></details>}
      <Textarea label="Outcome" value={f.outcome} disabled={approved} onChange={(e) => setF({ ...f, outcome: e.target.value })} />
      <Input label="Next date" type="date" value={f.next_date ?? ''} disabled={approved} onChange={(e) => setF({ ...f, next_date: e.target.value || null })} />
      <div className="vs-stack">
        <strong>Court directions (each becomes a task)</strong>
        {f.directions.length === 0 && <span className="vs-help">None found.</span>}
        {f.directions.map((d, i) => <Input key={i} label={`Direction ${i + 1}`} value={d.text} disabled={approved} onChange={(e) => edit(i, e.target.value)} />)}
      </div>
      <ErrorNote message={act.error} />
    </AIDraft>
  );
}

export function Hearings({ d, reload }: { d: Detail; reload: () => void }) {
  const { can } = useAuth();
  const [open, setOpen] = useState<string | null>(null);
  const [when, setWhen] = useState('');
  const [purpose, setPurpose] = useState('');
  const [clash, setClash] = useState<string[]>([]);
  const act = useAction();
  return (
    <div className="vs-stack">
      {can('calendar.write') && (
        <Card>
          <h3>Add a hearing date</h3>
          <div className="vs-row">
            <Input label="Date and time" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
            <Input label="Purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)} />
            <Button disabled={!when || act.busy} onClick={() => void act.run(async () => {
              const r = await api<{ clashes: { title: string }[] }>(`/cases/${d.id}/hearings`, { body: { hearing_at: new Date(when).toISOString(), purpose } });
              setClash(r.clashes.map((c) => c.title)); setWhen(''); setPurpose(''); reload();
            })}>Add</Button>
          </div>
          {clash.length > 0 && <div role="alert"><StatusTag tone="caution">Clash</StatusTag> <span className="vs-help">Another hearing is within an hour: {clash.join(', ')}. The date was still saved.</span></div>}
          <ErrorNote message={act.error} />
        </Card>
      )}
      {d.hearings.length === 0 ? <Empty>No hearings yet.</Empty> : d.hearings.map((h) => (
        <Card key={h.id}>
          <div className="vs-row" style={{ justifyContent: 'space-between' }}>
            <span><strong>{fmtDate(h.at)} {fmtTime(h.at)}</strong><div className="vs-help">{h.purpose ?? 'Hearing'}{h.court_room ? ` · ${h.court_room}` : ''}</div></span>
            <span className="vs-row"><StatusTag tone={h.status === 'scheduled' ? 'caution' : 'ok'}>{h.status}</StatusTag>
              {can('records.write') && <Button kind="secondary" onClick={() => setOpen(open === h.id ? null : h.id)}>{open === h.id ? 'Close' : 'Record'}</Button>}</span>
          </div>
          {open === h.id && <HearingRecords hearingId={h.id} onChange={reload} />}
        </Card>
      ))}
    </div>
  );
}

function HearingRecords({ hearingId, onChange }: { hearingId: string; onChange: () => void }) {
  const { data, reload } = useData<{ items: Rec[] }>(`/hearings/${hearingId}/records`);
  const [text, setText] = useState('');
  const [lang, setLang] = useState('en');
  const [recording, setRecording] = useState(false);
  const mr = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const act = useAction();
  const done = () => { reload(); onChange(); };
  const startVoice = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks.current = [];
    const r = new MediaRecorder(stream);
    r.ondataavailable = (e) => chunks.current.push(e.data);
    r.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      const form = new FormData();
      form.append('audio', new Blob(chunks.current, { type: r.mimeType }), 'hearing.webm');
      form.append('language', lang);
      void act.run(async () => { await upload(`/hearings/${hearingId}/records/audio`, form); done(); });
    };
    mr.current = r; r.start(); setRecording(true);
  };
  return (
    <div className="vs-stack" style={{ marginTop: 12 }}>
      <Select label="Language spoken" value={lang} onChange={(e) => setLang(e.target.value)}><option value="en">English</option><option value="ml">മലയാളം</option></Select>
      <Textarea label="Type what happened" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="vs-row">
        <Button disabled={!text.trim() || act.busy} onClick={() => void act.run(async () => { await api(`/hearings/${hearingId}/records`, { body: { text, language: lang } }); setText(''); done(); })}>Draft record from text</Button>
        {!recording
          ? <Button kind="secondary" onClick={() => void act.run(startVoice)}>Record voice</Button>
          : <Button kind="secondary" onClick={() => { mr.current?.stop(); setRecording(false); }}>Stop and draft</Button>}
      </div>
      <ErrorNote message={act.error} />
      {data?.items.map((r) => <RecordReview key={r.id} rec={r} onChange={done} />)}
    </div>
  );
}

type Task = { id: string; title: string; due_date: string | null; assignee_id: string | null; done: boolean; source: string };
export function CaseTasks({ caseId }: { caseId: string }) {
  const { can } = useAuth();
  const { data, reload } = useData<{ items: Task[] }>(`/tasks?case_id=${caseId}&done=false`);
  const dirs = useData<{ items: { id: string; text: string; due_date: string | null; done: boolean }[] }>(`/cases/${caseId}/directions`);
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const [dir, setDir] = useState('');
  const act = useAction();
  const refresh = () => { reload(); dirs.reload(); };
  return (
    <div className="vs-stack">
      {can('tasks.write') && (
        <Card>
          <h3>Add a task</h3>
          <div className="vs-row"><Input label="Task" value={title} onChange={(e) => setTitle(e.target.value)} /><Input label="Due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
            <Button disabled={!title || act.busy} onClick={() => void act.run(async () => { await api('/tasks', { body: { title, case_id: caseId, due_date: due || null } }); setTitle(''); setDue(''); refresh(); })}>Add task</Button></div>
          <h3>Note a court direction</h3>
          <div className="vs-row"><Input label="Direction" value={dir} onChange={(e) => setDir(e.target.value)} />
            <Button disabled={!dir || act.busy} onClick={() => void act.run(async () => { await api(`/cases/${caseId}/directions`, { body: { text: dir, due_date: due || null } }); setDir(''); refresh(); })}>Add direction</Button></div>
          <ErrorNote message={act.error} />
        </Card>
      )}
      <Card>
        <h3>Open tasks</h3>
        {!data || data.items.length === 0 ? <p className="vs-help">Nothing open.</p> : (
          <ul className="vs-list">{data.items.map((t) => (
            <li key={t.id}><span>{t.title}{t.source === 'direction' && <> <StatusTag tone="caution">Court direction</StatusTag></>}<div className="vs-help">Due {fmtDate(t.due_date)}</div></span>
              {can('tasks.write') && <Button kind="secondary" onClick={() => void act.run(async () => { await api(`/tasks/${t.id}`, { method: 'PATCH', body: { done: true } }); refresh(); })}>Mark done</Button>}</li>
          ))}</ul>
        )}
      </Card>
    </div>
  );
}

type Doc = { id: string; name: string; doc_type: string | null; uploaded_at: string; has_text: boolean; ai_status: string; ai?: AI | null; text_preview?: string };
type AI = { summary: string; dates: { date: string; what: string; page: number | null }[]; parties: { name: string; page: number | null }[]; sections: { ref: string; page: number | null }[]; orders: string[] };

function DocRow({ doc, onChange }: { doc: Doc; onChange: () => void }) {
  const { can } = useAuth();
  const [full, setFull] = useState<Doc | null>(null);
  const act = useAction();
  const view = () => act.run(async () => setFull(await api<Doc>(`/documents/${doc.id}`)));
  return (
    <li style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <div className="vs-row" style={{ justifyContent: 'space-between' }}>
        <span><strong>{doc.name}</strong><div className="vs-help">{doc.doc_type ?? 'Document'} · {fmtDate(doc.uploaded_at)}</div></span>
        <span className="vs-row">
          {doc.ai_status !== 'none' && <StatusTag tone={doc.ai_status === 'approved' ? 'ok' : 'caution'}>AI {doc.ai_status}</StatusTag>}
          <Button kind="secondary" onClick={() => void act.run(() => download(`/documents/${doc.id}/download`, doc.name))}>Download</Button>
          <Button kind="secondary" onClick={() => void view()}>Open</Button>
          {can('docs.write') && <Confirm label="Delete" onConfirm={() => void act.run(async () => { await api(`/documents/${doc.id}`, { method: 'DELETE' }); onChange(); })} />}
        </span>
      </div>
      <ErrorNote message={act.error} />
      {full && (
        <div className="vs-stack">
          {full.ai ? (
            <AIDraft title="Summary" approved={full.ai_status === 'approved'}
              actions={full.ai_status === 'draft' && can('records.approve') ? <Button onClick={() => void act.run(async () => { await api(`/documents/${doc.id}/ai/approve`, { body: {} }); setFull(await api<Doc>(`/documents/${doc.id}`)); onChange(); })}>Approve summary</Button> : undefined}>
              <p>{full.ai.summary}</p>
              {full.ai.dates.length > 0 && <><strong>Dates</strong><ul>{full.ai.dates.map((x, i) => <li key={i}>{x.date}: {x.what}{x.page ? ` (page ${x.page})` : ''}</li>)}</ul></>}
              {full.ai.orders.length > 0 && <><strong>Orders</strong><ul>{full.ai.orders.map((x, i) => <li key={i}>{x}</li>)}</ul></>}
            </AIDraft>
          ) : doc.has_text && can('docs.write') ? <Button kind="secondary" onClick={() => void act.run(async () => { setFull(await api<Doc>(`/documents/${doc.id}/summarize`, { body: {} })); onChange(); })}>Summarise with AI</Button>
            : <p className="vs-help">{doc.has_text ? '' : 'No text could be read from this file.'}</p>}
          {full.text_preview && <details><summary className="vs-help">Text read from the file</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{full.text_preview}</pre></details>}
        </div>
      )}
    </li>
  );
}

export function Documents({ caseId }: { caseId: string }) {
  const { can } = useAuth();
  const [q, setQ] = useState('');
  const { data, reload } = useData<{ items: Doc[] }>(`/cases/${caseId}/documents${q ? `?q=${encodeURIComponent(q)}` : ''}`);
  const act = useAction();
  const onFile = (file: File | undefined) => {
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    void act.run(async () => { await upload(`/cases/${caseId}/documents`, form); reload(); });
  };
  return (
    <div className="vs-stack">
      <div className="vs-row">
        <Input label="Search inside documents" value={q} onChange={(e) => setQ(e.target.value)} />
        {can('docs.write') && <div className="vs-field"><label htmlFor="upl">Upload (PDF, image or text)</label><input id="upl" type="file" accept="application/pdf,image/*,text/plain" onChange={(e) => onFile(e.target.files?.[0])} /></div>}
      </div>
      <ErrorNote message={act.error} />
      <Card>{!data || data.items.length === 0 ? <p className="vs-help">No documents.</p> : <ul className="vs-list">{data.items.map((d) => <DocRow key={d.id} doc={d} onChange={reload} />)}</ul>}</Card>
    </div>
  );
}

type Msg = { id: string; kind: string; body: string; status: string; channel: string | null };
type Chat = { id: string; from_client: boolean; body: string };
export function Messages({ caseId }: { caseId: string }) {
  const { can } = useAuth();
  const { data, reload } = useData<{ items: Msg[] }>(`/cases/${caseId}/messages`);
  const chat = useData<{ items: Chat[] }>(`/cases/${caseId}/chat`);
  const [custom, setCustom] = useState('');
  const [reply, setReply] = useState('');
  const [link, setLink] = useState<string | null>(null);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [share, setShare] = useState<string | null>(null);
  const act = useAction();
  return (
    <div className="vs-stack">
      <Card>
        <h3>Messages to the client</h3>
        <p className="vs-help">Drafts need approval. Nothing is sent until a Director has switched client messages on.</p>
        <Textarea label="Write a message" value={custom} onChange={(e) => setCustom(e.target.value)} />
        <Button disabled={!custom || act.busy} onClick={() => void act.run(async () => { await api(`/cases/${caseId}/messages`, { body: { body: custom } }); setCustom(''); reload(); })}>Save as draft</Button>
        <ErrorNote message={act.error} />
      </Card>
      {data?.items.map((m) => (
        <AIDraft key={m.id} title={m.kind.replace('_', ' ')} approved={m.status !== 'draft'}
          actions={<>
            {m.status === 'draft' && <Button kind="secondary" onClick={() => void act.run(async () => { await api(`/messages/${m.id}`, { method: 'PATCH', body: { body: edit[m.id] ?? m.body } }); reload(); })}>Save edits</Button>}
            {m.status === 'draft' && can('messages.approve') && <Button onClick={() => void act.run(async () => { await api(`/messages/${m.id}/approve`, { body: {} }); reload(); })}>Approve</Button>}
            {m.status !== 'draft' && can('messages.approve') && (['email', 'push', 'whatsapp'] as const).map((ch) => (
              <Button key={ch} kind="secondary" onClick={() => void act.run(async () => { const r = await api<{ link?: string }>(`/messages/${m.id}/send`, { body: { channel: ch } }); if (r.link) setLink(r.link); reload(); })}>Send by {ch}</Button>
            ))}
            {m.status === 'sent' && <StatusTag tone="ok">Sent by {m.channel}</StatusTag>}
          </>}>
          <Textarea label="Message" value={edit[m.id] ?? m.body} disabled={m.status !== 'draft'} onChange={(e) => setEdit({ ...edit, [m.id]: e.target.value })} />
        </AIDraft>
      ))}
      {link && <Card><p>WhatsApp is ready. You press send yourself:</p><a href={link} target="_blank" rel="noreferrer">Open WhatsApp</a></Card>}
      {can('messages.approve') && (
        <Card>
          <h3>Client access</h3>
          <div className="vs-row">
            <Button kind="secondary" onClick={() => void act.run(async () => { const r = await api<{ url: string }>(`/cases/${caseId}/share`, { body: { days: 14 } }); setShare(r.url); })}>Create status link (14 days)</Button>
            <Button kind="text" onClick={() => void act.run(async () => { await api(`/cases/${caseId}/share`, { method: 'DELETE' }); setShare(null); })}>Turn off all links</Button>
          </div>
          {share && <p>Share this read-only link: <code>{share}</code></p>}
          <h3>Chat with client</h3>
          <div className="vs-chat">{chat.data?.items.map((m) => <div key={m.id} className={`vs-bubble${m.from_client ? '' : ' vs-bubble--me'}`}>{m.body}</div>)}</div>
          <div className="vs-row"><Input label="Reply" value={reply} onChange={(e) => setReply(e.target.value)} />
            <Button disabled={!reply} onClick={() => void act.run(async () => { await api(`/cases/${caseId}/chat`, { body: { body: reply } }); setReply(''); chat.reload(); })}>Send</Button></div>
        </Card>
      )}
    </div>
  );
}
