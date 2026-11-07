import { useCallback, useEffect, useId, useState } from 'react';
import type { ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { api, ApiError } from './auth/api';
import { Button, Card } from './components';

export const inr = (paise: number) => `₹${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export const fmtDate = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString('en-IN', { dateStyle: 'medium' }) : '—');
export const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });

/** Loads a path and reloads on demand. `null` while loading. */
export function useData<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    if (!path) return;
    api<T>(path).then((d) => { setData(d); setError(null); }).catch((e: unknown) => setError(e instanceof ApiError ? e.message : 'Could not load'));
  }, [path]);
  useEffect(() => { setData(null); load(); }, [load]);
  return { data, error, reload: load };
}

/** Runs an action and shows its error in place. */
export function useAction() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setError(null);
    try { return await fn(); } catch (e) { setError(e instanceof ApiError ? e.message : 'Something went wrong'); } finally { setBusy(false); }
  };
  return { error, busy, run, clear: () => setError(null) };
}

export function ErrorNote({ message }: { message: string | null }) {
  return message ? <div role="alert" className="vs-help vs-help--error">{message}</div> : null;
}

export function Select({ label, children, ...p }: SelectHTMLAttributes<HTMLSelectElement> & { label: string; children: ReactNode }) {
  const id = useId();
  return <div className="vs-field"><label htmlFor={id}>{label}</label><select id={id} {...p} className="vs-input">{children}</select></div>;
}

export function Textarea({ label, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string }) {
  const id = useId();
  return <div className="vs-field"><label htmlFor={id}>{label}</label><textarea id={id} {...p} className="vs-input vs-textarea" /></div>;
}

export function PageHead({ title, help, actions }: { title: string; help?: string; actions?: ReactNode }) {
  return (
    <div className="vs-row" style={{ justifyContent: 'space-between' }}>
      <div><h1>{title}</h1>{help && <div className="vs-help">{help}</div>}</div>
      {actions && <div className="vs-row">{actions}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <Card><p className="vs-help">{children}</p></Card>;
}

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: string }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div className="vs-tabs" role="tablist">
      {tabs.map((t) => <button key={t.key} role="tab" aria-selected={t.key === active} onClick={() => onChange(t.key)}>{t.label}</button>)}
    </div>
  );
}

export function Confirm({ label, onConfirm, kind = 'secondary' }: { label: string; onConfirm: () => void; kind?: 'primary' | 'secondary' | 'text' }) {
  const [ask, setAsk] = useState(false);
  if (!ask) return <Button kind={kind} onClick={() => setAsk(true)}>{label}</Button>;
  return <span className="vs-row"><span className="vs-help">Are you sure?</span><Button onClick={() => { setAsk(false); onConfirm(); }}>Yes, {label.toLowerCase()}</Button><Button kind="text" onClick={() => setAsk(false)}>Cancel</Button></span>;
}
