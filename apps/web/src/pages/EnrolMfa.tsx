import { useEffect, useState, type FormEvent } from 'react';
import { ApiError, api } from '../auth/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, Input } from '../components';

export function EnrolMfa() {
  const { refresh, signOut } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api<{ secret: string; otpauth_uri: string }>('/auth/mfa/setup', { method: 'POST' }).then(setSetup); }, []);
  async function submit(e: FormEvent) {
    e.preventDefault();
    try { await api('/auth/mfa/enable', { body: { code } }); await refresh(); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Could not verify'); }
  }
  return (
    <main className="vs-auth">
      <form className="vs-auth__box" onSubmit={submit} aria-label="Set up two-factor sign-in">
        <h1>Set up two-factor sign-in</h1>
        <p className="vs-help">Your office requires it for your role. Add this key to an authenticator app, then enter the 6-digit code.</p>
        {setup && <p><code data-testid="secret">{setup.secret}</code></p>}
        <Input label="6-digit code" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} error={error ?? undefined} required />
        <Button type="submit">Turn on</Button>
        <Button type="button" kind="text" onClick={() => void signOut()}>Sign out</Button>
      </form>
    </main>
  );
}
