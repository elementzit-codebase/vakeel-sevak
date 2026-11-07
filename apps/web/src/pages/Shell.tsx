import { useEffect, useState } from 'react';
import { api } from '../auth/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, Card } from '../components';
import { t, type Messages } from '../i18n';
import type { AppConfig } from '../config';
import { Input } from '../components';
import { Empty, ErrorNote, fmtDate, useAction, useData } from '../ui';
import { CaseWorkspace } from './CaseWorkspace';
import { CasesPage } from './Cases';
import { ClientsPage } from './Clients';
import { CalendarPage, ImportPage, TasksPage } from './Planner';
import { AskPage, ConsultPage, FeesPage, StatutesPage } from './Library';
import { TeamAccess } from './TeamAccess';
import { TodayPage } from './Today';

type Nav = { key: string; label: keyof Messages; perm: readonly string[] | null };
const NAV: Nav[] = [
  { key: 'home', label: 'today', perm: null },
  { key: 'cases', label: 'cases', perm: ['cases.read_all', 'cases.read_assigned'] },
  { key: 'clients', label: 'clients', perm: ['clients.read'] },
  { key: 'calendar', label: 'calendar', perm: ['calendar.read'] },
  { key: 'tasks', label: 'tasks', perm: ['tasks.read'] },
  { key: 'fees', label: 'fees', perm: ['fees.read'] },
  { key: 'library', label: 'library', perm: ['cases.read_all', 'cases.read_assigned'] },
  { key: 'consult', label: 'consult', perm: ['consult.write'] },
  { key: 'ask', label: 'ask', perm: ['ask.use'] },
  { key: 'team', label: 'team', perm: ['audit.read'] },
];

export function Shell({ config }: { config: AppConfig }) {
  const { user, can, signOut } = useAuth();
  const [page, setPage] = useState('home');
  const [caseId, setCaseId] = useState<string | null>(null);
  const [clientsKey, setClientsKey] = useState(0);
  const items = NAV.filter((n) => !n.perm || n.perm.some(can));
  if (!user) return null;
  const lang = user.language;
  const go = (k: string) => { setPage(k); setCaseId(null); };
  const openCase = (id: string) => { setCaseId(id); setPage('cases'); };
  const body = () => {
    if (caseId) return <CaseWorkspace id={caseId} onBack={() => setCaseId(null)} />;
    switch (page) {
      case 'cases': return <CasesPage onOpen={openCase} onImport={() => setPage('import')} />;
      case 'import': return <ImportPage onDone={() => go('cases')} />;
      case 'clients': return <ClientsPage key={clientsKey} onOpenCase={openCase} />;
      case 'calendar': return <CalendarPage onOpenCase={openCase} />;
      case 'tasks': return <TasksPage onOpenCase={openCase} />;
      case 'fees': return <FeesPage onOpenClient={() => { setClientsKey(clientsKey + 1); go('clients'); }} />;
      case 'library': return <StatutesPage />;
      case 'consult': return <ConsultPage />;
      case 'ask': return <AskPage />;
      case 'team': return <TeamAccess />;
      default: return <TodayPage onOpenCase={openCase} />;
    }
  };
  const allowed = page === 'home' || page === 'import' || items.some((i) => i.key === page);
  return (
    <div className="vs-shell">
      <aside className="vs-rail">
        <strong className="vs-rail__brand">{config.product_name}</strong>
        <nav aria-label="Main">
          {items.map((n) => (
            <button key={n.key} className="vs-rail__item" aria-current={page === n.key && !caseId ? 'page' : undefined} onClick={() => go(n.key)}>{t(lang, n.label)}</button>
          ))}
        </nav>
        <div className="vs-rail__user">
          <div>{user.name}</div><div className="vs-help">{user.role}</div>
          <Button kind="secondary" onClick={() => void signOut()}>{t(lang, 'signOut')}</Button>
        </div>
      </aside>
      <main className="vs-main">{allowed ? body() : <AccessDenied />}</main>
    </div>
  );
}

export function AccessDenied() {
  return <Card><h2>No access</h2><p>Your role cannot open this page. Ask your Director if you need it.</p></Card>;
}

type Portal = { id: string; title: string; case_number: string; stage: string; next_hearing: string | null };
type Chat = { id: string; from_client: boolean; body: string };

function ClientChat({ caseId }: { caseId: string }) {
  const { data, error, reload } = useData<{ items: Chat[] }>(`/portal/cases/${caseId}/chat`);
  const [text, setText] = useState('');
  const act = useAction();
  if (error) return <p className="vs-help">{error}</p>;
  return (
    <div className="vs-stack">
      <div className="vs-chat">{data?.items.map((m) => <div key={m.id} className={`vs-bubble${m.from_client ? ' vs-bubble--me' : ''}`}>{m.body}</div>)}</div>
      <div className="vs-row"><Input label="Message your advocate" value={text} onChange={(e) => setText(e.target.value)} />
        <Button disabled={!text || act.busy} onClick={() => void act.run(async () => { await api(`/portal/cases/${caseId}/chat`, { body: { body: text } }); setText(''); reload(); })}>Send</Button></div>
      <ErrorNote message={act.error} />
    </div>
  );
}

export function ClientHome({ config }: { config: AppConfig }) {
  const { user, signOut } = useAuth();
  const [items, setItems] = useState<Portal[]>([]);
  useEffect(() => { api<{ items: Portal[] }>('/portal/cases').then((r) => setItems(r.items)); }, []);
  return (
    <main className="vs-page">
      <header className="vs-row" style={{ justifyContent: 'space-between' }}>
        <div><h1>{config.product_name}</h1><div className="vs-help">Your cases, read only · {user?.name}</div></div>
        <Button kind="secondary" onClick={() => void signOut()}>Sign out</Button>
      </header>
      {items.length === 0 && <Empty>No cases to show.</Empty>}
      {items.map((c) => (
        <Card key={c.id}>
          <h2>{c.title}</h2>
          <div className="vs-help">{c.case_number} · {c.stage}</div>
          <p>Next hearing: {c.next_hearing ? fmtDate(c.next_hearing) : 'not fixed yet'}</p>
          <ClientChat caseId={c.id} />
        </Card>
      ))}
    </main>
  );
}
