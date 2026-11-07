import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react';
import { useId } from 'react';

export function Button({ kind = 'primary', ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { kind?: 'primary' | 'secondary' | 'text' }) {
  return <button {...p} className={`vs-btn vs-btn--${kind}`} />;
}

export function Input({ label, help, error, ...p }: InputHTMLAttributes<HTMLInputElement> & { label: string; help?: string; error?: string }) {
  const id = useId();
  return (
    <div className="vs-field">
      <label htmlFor={id}>{label}</label>
      <input id={id} {...p} className="vs-input" aria-invalid={error ? 'true' : undefined} aria-describedby={`${id}-h`} />
      {(error || help) && <div id={`${id}-h`} className={`vs-help${error ? ' vs-help--error' : ''}`}>{error ?? help}</div>}
    </div>
  );
}

export type Tone = 'alert' | 'caution' | 'ok' | 'neutral';
const ICON: Record<Tone, string> = { alert: '⚠', caution: '◷', ok: '✓', neutral: '' };

/** Status is always shown as icon plus word, never colour alone. */
export function StatusTag({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`vs-tag vs-tag--${tone}`}>{ICON[tone] && <span aria-hidden="true">{ICON[tone]}</span>}{children}</span>;
}

export function Card({ children }: { children: ReactNode }) {
  return <div className="vs-card">{children}</div>;
}

/** AI output stays a dashed Draft until the advocate approves it. */
export function AIDraft({ title, approved = false, children, actions }: { title: string; approved?: boolean; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className={`vs-ai${approved ? ' vs-ai--approved' : ''}`}>
      <div className="vs-ai__head">
        <span className="vs-badge">AI</span>
        <span>{title}</span>
        {approved ? <StatusTag tone="ok">Approved</StatusTag> : <span className="vs-draft">Draft</span>}
      </div>
      <div>{children}</div>
      {actions && <div className="vs-row">{actions}</div>}
    </section>
  );
}

export type Tab = { key: string; label: string };
export function TabBar({ tabs, active, onChange }: { tabs: Tab[]; active: string; onChange: (key: string) => void }) {
  return (
    <nav className="vs-tabbar" aria-label="Main">
      {tabs.map((t) => (
        <button key={t.key} className="vs-tab" aria-current={t.key === active ? 'page' : undefined} onClick={() => onChange(t.key)}>
          {t.label}
        </button>
      ))}
    </nav>
  );
}

export type Column<T> = { header: string; cell: (row: T) => ReactNode };
export function DataTable<T>({ columns, rows, rowKey }: { columns: Column<T>[]; rows: T[]; rowKey: (row: T) => string }) {
  return (
    <table className="vs-table">
      <thead><tr>{columns.map((c) => <th key={c.header}>{c.header}</th>)}</tr></thead>
      <tbody>{rows.map((r) => <tr key={rowKey(r)}>{columns.map((c) => <td key={c.header}>{c.cell(r)}</td>)}</tr>)}</tbody>
    </table>
  );
}
