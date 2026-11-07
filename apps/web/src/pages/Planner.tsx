import { useState } from 'react';
import { api, upload } from '../auth/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, Card, DataTable, Input, StatusTag } from '../components';
import { Empty, ErrorNote, PageHead, Select, fmtDate, fmtTime, useAction, useData } from '../ui';

type Item = { type: string; id: string; at: string; title: string; detail: string | null; case_id: string | null; status?: string };

export function CalendarPage({ onOpenCase }: { onOpenCase: (id: string) => void }) {
  const { can } = useAuth();
  const [start, setStart] = useState(new Date().toISOString().slice(0, 10));
  const s = new Date(`${start}T00:00:00`);
  const e = new Date(s.getTime() + 14 * 86400000);
  const { data, reload } = useData<{ items: Item[] }>(`/calendar?start=${encodeURIComponent(s.toISOString())}&end=${encodeURIComponent(e.toISOString())}`);
  const [f, setF] = useState({ title: '', at: '' });
  const act = useAction();
  const days = new Map<string, Item[]>();
  data?.items.forEach((i) => { const k = i.at.slice(0, 10); days.set(k, [...(days.get(k) ?? []), i]); });
  return (
    <>
      <PageHead title="Calendar" help="Next 14 days from the date below" />
      <Input label="From" type="date" value={start} onChange={(ev) => setStart(ev.target.value)} />
      {can('calendar.write') && (
        <Card>
          <div className="vs-row"><Input label="Add a meeting or reminder" value={f.title} onChange={(ev) => setF({ ...f, title: ev.target.value })} />
            <Input label="When" type="datetime-local" value={f.at} onChange={(ev) => setF({ ...f, at: ev.target.value })} />
            <Button disabled={!f.title || !f.at || act.busy} onClick={() => void act.run(async () => { await api('/calendar', { body: { title: f.title, starts_at: new Date(f.at).toISOString() } }); setF({ title: '', at: '' }); reload(); })}>Add</Button></div>
          <ErrorNote message={act.error} />
        </Card>
      )}
      {days.size === 0 ? <Empty>Nothing scheduled in this period.</Empty> : [...days.entries()].map(([day, items]) => (
        <Card key={day}>
          <h3>{fmtDate(day)}</h3>
          <ul className="vs-list">{items.map((i) => (
            <li key={i.id}><span>{i.case_id ? <button className="vs-link" onClick={() => onOpenCase(i.case_id!)}>{i.title}</button> : i.title}<div className="vs-help">{i.detail}</div></span>
              <span className="vs-row">{i.type === 'hearing' && <StatusTag tone="caution">Hearing</StatusTag>}<strong>{fmtTime(i.at)}</strong></span></li>
          ))}</ul>
        </Card>
      ))}
    </>
  );
}

type Task = { id: string; title: string; case_id: string | null; case_title: string | null; due_date: string | null; done: boolean; source: string };
export function TasksPage({ onOpenCase }: { onOpenCase: (id: string) => void }) {
  const { can } = useAuth();
  const [mine, setMine] = useState(false);
  const { data, reload } = useData<{ items: Task[] }>(`/tasks?done=false${mine ? '&mine=true' : ''}`);
  const [title, setTitle] = useState('');
  const act = useAction();
  const today = new Date().toISOString().slice(0, 10);
  return (
    <>
      <PageHead title="Tasks" actions={<label className="vs-check"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Only mine</label>} />
      {can('tasks.write') && <div className="vs-row"><Input label="New task" value={title} onChange={(e) => setTitle(e.target.value)} /><Button disabled={!title || act.busy} onClick={() => void act.run(async () => { await api('/tasks', { body: { title } }); setTitle(''); reload(); })}>Add</Button></div>}
      <ErrorNote message={act.error} />
      {data && <DataTable rows={data.items} rowKey={(r) => r.id} columns={[
        { header: 'Task', cell: (r) => <>{r.title} {r.source === 'direction' && <StatusTag tone="caution">Direction</StatusTag>}</> },
        { header: 'Case', cell: (r) => r.case_id ? <button className="vs-link" onClick={() => onOpenCase(r.case_id!)}>{r.case_title}</button> : '—' },
        { header: 'Due', cell: (r) => r.due_date && r.due_date < today ? <StatusTag tone="alert">Overdue {fmtDate(r.due_date)}</StatusTag> : fmtDate(r.due_date) },
        { header: '', cell: (r) => can('tasks.write') ? <Button kind="secondary" onClick={() => void act.run(async () => { await api(`/tasks/${r.id}`, { method: 'PATCH', body: { done: true } }); reload(); })}>Done</Button> : null },
      ]} />}
    </>
  );
}

type Row = { row: number; status: string; errors: string[]; warnings: string[]; data: Record<string, string | null> };
type Preview = { total: number; ok: number; skip: number; errors: number; rows: Row[] };
export function ImportPage({ onDone }: { onDone: () => void }) {
  const [pv, setPv] = useState<Preview | null>(null);
  const [res, setRes] = useState<{ created: number; skipped: number } | null>(null);
  const act = useAction();
  const pick = (file?: File) => {
    if (!file) return;
    const form = new FormData(); form.append('file', file);
    void act.run(async () => { setRes(null); setPv(await upload<Preview>('/import/preview', form)); });
  };
  return (
    <>
      <Button kind="text" onClick={onDone}>← Cases</Button>
      <PageHead title="Import cases" help="Columns: Title, Case Number, Court, Client, Stage, Next Date. Nothing is saved until you confirm." />
      <div className="vs-field"><label htmlFor="imp">Excel (.xlsx) or CSV file</label><input id="imp" type="file" accept=".xlsx,.csv" onChange={(e) => pick(e.target.files?.[0])} /></div>
      <ErrorNote message={act.error} />
      {pv && (
        <>
          <div className="vs-row"><StatusTag tone="ok">{pv.ok} ready</StatusTag><StatusTag tone="caution">{pv.skip} will be skipped</StatusTag><StatusTag tone="alert">{pv.errors} with errors</StatusTag></div>
          <DataTable rows={pv.rows} rowKey={(r) => String(r.row)} columns={[
            { header: 'Row', cell: (r) => r.row },
            { header: 'Case', cell: (r) => <>{r.data.title}<div className="vs-help">{r.data.case_number} · {r.data.client}</div></> },
            { header: 'Result', cell: (r) => r.status === 'ok' ? <StatusTag tone="ok">Ready</StatusTag> : <StatusTag tone={r.status === 'error' ? 'alert' : 'caution'}>{[...r.errors, ...r.warnings].join('; ')}</StatusTag> },
          ]} />
          {!res && <Button disabled={pv.ok === 0 || act.busy} onClick={() => void act.run(async () => setRes(await api('/import/commit', { body: { rows: pv.rows.map((r) => r.data) } })))}>Import {pv.ok} cases</Button>}
          {res && <Card><p>{res.created} cases imported, {res.skipped} skipped.</p><Button onClick={onDone}>View cases</Button></Card>}
        </>
      )}
    </>
  );
}
