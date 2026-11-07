import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, getToken, setOnExpired, setToken, type User } from './api';

type Ctx = {
  user: User | null;
  enrolRequired: boolean;
  notice: string | null;
  setSession: (token: string, user: User, enrolRequired: boolean) => void;
  signOut: (notice?: string) => Promise<void>;
  can: (permission: string) => boolean;
  refresh: () => Promise<void>;
};
const AuthCtx = createContext<Ctx | null>(null);
export const useAuth = () => {
  const c = useContext(AuthCtx);
  if (!c) throw new Error('useAuth outside AuthProvider');
  return c;
};

const ACTIVITY = ['click', 'keydown', 'pointerdown', 'scroll', 'touchstart'] as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [enrolRequired, setEnrol] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [ready, setReady] = useState(!getToken());
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const clear = useCallback((msg: string | null) => { setUser(null); setEnrol(false); setNotice(msg); }, []);
  const signOut = useCallback(async (msg?: string) => {
    try { if (getToken()) await api('/auth/logout', { method: 'POST', body: undefined }); } catch { /* already ended */ }
    setToken(null);
    clear(msg ?? null);
  }, [clear]);

  const refresh = useCallback(async () => {
    const me = await api<User & { mfa_enrollment_required: boolean }>('/auth/me');
    setUser(me); setEnrol(me.mfa_enrollment_required);
  }, []);

  useEffect(() => {
    setOnExpired((m) => clear(m));
    if (getToken()) refresh().catch(() => clear(null)).finally(() => setReady(true));
  }, [clear, refresh]);

  // AUT-05: end the web session after the office's idle time (30 minutes) without activity.
  useEffect(() => {
    if (!user) return;
    const ms = user.idle_minutes * 60_000;
    const reset = () => {
      clearTimeout(timer.current);
      timer.current = setTimeout(() => { void signOut(`You were signed out after ${user.idle_minutes} minutes of inactivity.`); }, ms);
    };
    reset();
    ACTIVITY.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    return () => { clearTimeout(timer.current); ACTIVITY.forEach((e) => window.removeEventListener(e, reset)); };
  }, [user, signOut]);

  const value: Ctx = {
    user, enrolRequired, notice, signOut, refresh,
    setSession: (t, u, e) => { setToken(t); setUser(u); setEnrol(e); setNotice(null); },
    can: (p) => !!user?.permissions.includes(p),
  };
  return <AuthCtx.Provider value={value}>{ready ? children : null}</AuthCtx.Provider>;
}
