import { useAuth } from '../auth/AuthProvider';
import { Card, StatusTag } from '../components';
import { Empty, PageHead, fmtDate, fmtTime, useData } from '../ui';

type Item = { type: string; id: string; at: string; title: string; detail: string | null; court?: string; room?: string | null; case_id: string | null; status?: string };
type Task = { id: string; title: string; case_id: string | null; case_title: string | null; due_date: string | null; overdue: boolean };
type Alert = { case_id: string; title: string; rule: string; severity: string; message: string };
type Today = { date: string; hearings_today: Item[]; week: Item[]; tasks: Task[]; alerts: Alert[] };

export function TodayPage({ onOpenCase }: { onOpenCase: (id: string) => void }) {
  const { user } = useAuth();
  const { data, error } = useData<Today>('/today');
  if (error) return <Empty>{error}</Empty>;
  if (!data) return null;
  const open = (id: string | null) => id && onOpenCase(id);
  return (
    <>
      <PageHead title={`Good day, ${user?.name ?? ''}`} help={fmtDate(data.date)} />
      {data.alerts.length > 0 && (
        <Card>
          <h2>Needs attention</h2>
          <ul className="vs-list">
            {data.alerts.map((a, i) => (
              <li key={i}>
                <span><button className="vs-link" onClick={() => open(a.case_id)}>{a.title}</button><div className="vs-help">{a.message}</div></span>
                <StatusTag tone={a.severity === 'high' ? 'alert' : 'caution'}>{a.rule.replace(/_/g, ' ')}</StatusTag>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card>
        <h2>Today in court</h2>
        {data.hearings_today.length === 0 ? <p className="vs-help">No hearings today.</p> : (
          <ul className="vs-list">
            {data.hearings_today.map((h) => (
              <li key={h.id}>
                <span><button className="vs-link" onClick={() => open(h.case_id)}>{h.title}</button><div className="vs-help">{h.detail} · {h.court}{h.room ? ` · ${h.room}` : ''}</div></span>
                <strong>{fmtTime(h.at)}</strong>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <h2>Tasks due</h2>
        {data.tasks.length === 0 ? <p className="vs-help">Nothing due today or overdue.</p> : (
          <ul className="vs-list">
            {data.tasks.map((t) => (
              <li key={t.id}><span>{t.title}<div className="vs-help">{t.case_title ?? 'General'}</div></span>
                {t.overdue ? <StatusTag tone="alert">Overdue {fmtDate(t.due_date)}</StatusTag> : <StatusTag tone="caution">Due {fmtDate(t.due_date)}</StatusTag>}</li>
            ))}
          </ul>
        )}
      </Card>
      {data.week.length > 0 && (
        <Card>
          <h2>Coming up this week</h2>
          <ul className="vs-list">
            {data.week.map((h) => <li key={h.id}><span>{h.title}<div className="vs-help">{h.detail}</div></span><span>{fmtDate(h.at)} {fmtTime(h.at)}</span></li>)}
          </ul>
        </Card>
      )}
    </>
  );
}
