import { useState, type FormEvent } from 'react';
import { ApiError, api } from '../auth/api';
import { Button, Input } from '../components';

export function Forgot({ onBack }: { onBack: () => void }) {
  const [email, setEmail] = useState('');
  const [done, setDone] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    await api('/auth/password/forgot', { body: { email: email.trim() } }).catch(() => undefined);
    setDone(true);
  }
  return (
    <main className="vs-auth">
      <form className="vs-auth__box" onSubmit={submit} aria-label="Forgot password">
        <h1>Reset your password</h1>
        {done ? (
          <p role="status">If that email has an account, a reset link has been sent. It works once and expires in 30 minutes.</p>
        ) : (
          <>
            <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <Button type="submit">Send reset link</Button>
          </>
        )}
        <Button type="button" kind="text" onClick={onBack}>Back to sign in</Button>
      </form>
    </main>
  );
}

export function ResetPassword({ token, onDone }: { token: string; onDone: () => void }) {
  const [pw, setPw] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try { await api('/auth/password/reset', { body: { token, new_password: pw } }); setOk(true); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Could not reset the password'); }
  }
  return (
    <main className="vs-auth">
      <form className="vs-auth__box" onSubmit={submit} aria-label="Choose a new password">
        <h1>Choose a new password</h1>
        {ok ? <p role="status">Password changed. Sign in with the new password.</p> : (
          <>
            <Input label="New password" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)}
              help="At least 10 characters." error={error ?? undefined} required />
            <Button type="submit">Change password</Button>
          </>
        )}
        <Button type="button" kind={ok ? 'primary' : 'text'} onClick={onDone}>Go to sign in</Button>
      </form>
    </main>
  );
}
