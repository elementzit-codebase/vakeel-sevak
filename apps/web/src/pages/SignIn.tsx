import { useState, type FormEvent } from 'react';
import { ApiError, login } from '../auth/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, Input } from '../components';
import type { AppConfig } from '../config';

export function SignIn({ config, onForgot }: { config: AppConfig; onForgot: () => void }) {
  const { setSession, notice } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [needOtp, setNeedOtp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const r = await login(email.trim(), password, needOtp ? otp : undefined);
      if ('mfa_required' in r) setNeedOtp(true);
      else setSession(r.access_token, r.user, r.mfa_enrollment_required);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reach the server');
    } finally { setBusy(false); }
  }

  return (
    <main className="vs-auth">
      <form className="vs-auth__box" onSubmit={submit} aria-label="Sign in">
        <h1>Sign in to your chambers</h1>
        <p className="vs-help">{config.product_name}. Use the email your office registered for you.</p>
        {notice && <p role="status" className="vs-help">{notice}</p>}
        <Input label="Email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <Input label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {needOtp && (
          <Input label="Code from your authenticator app" inputMode="numeric" autoComplete="one-time-code" value={otp}
            onChange={(e) => setOtp(e.target.value)} help="Enter the 6-digit code." required />
        )}
        {error && <p role="alert" className="vs-help vs-help--error">{error}</p>}
        <Button type="submit" disabled={busy}>{needOtp ? 'Verify and sign in' : 'Sign in'}</Button>
        <Button type="button" kind="text" onClick={onForgot}>Forgot password?</Button>
      </form>
    </main>
  );
}
