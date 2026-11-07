import { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from './auth/AuthProvider';
import { loadConfig, type AppConfig } from './config';
import { EnrolMfa } from './pages/EnrolMfa';
import { Forgot, ResetPassword } from './pages/PasswordPages';
import { Gallery } from './pages/Gallery';
import { ClientHome, Shell } from './pages/Shell';
import { PublicStatus } from './pages/PublicStatus';
import { SignIn } from './pages/SignIn';

function Routes({ config, lang, setLang }: { config: AppConfig; lang: string; setLang: (l: string) => void }) {
  const { user, enrolRequired } = useAuth();
  const params = new URLSearchParams(window.location.search);
  const [view, setView] = useState<'in' | 'forgot'>('in');
  const resetToken = params.get('token');
  if (params.has('gallery')) return <Gallery config={config} lang={lang} setLang={setLang} />;
  if (!user) {
    if (resetToken) return <ResetPassword token={resetToken} onDone={() => { window.history.replaceState({}, '', '/'); setView('in'); window.location.reload(); }} />;
    return view === 'forgot' ? <Forgot onBack={() => setView('in')} /> : <SignIn config={config} onForgot={() => setView('forgot')} />;
  }
  if (enrolRequired) return <EnrolMfa />;
  return user.role === 'client' ? <ClientHome config={config} /> : <Shell config={config} />;
}

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [lang, setLang] = useState('en');
  useEffect(() => {
    loadConfig().then((c) => { setConfig(c); setLang(c.default_language); document.title = c.product_name; });
  }, []);
  if (!config) return null;
  const m = window.location.pathname.match(/^\/status\/([\w-]+)$/);
  if (m) return <PublicStatus token={m[1]} />;
  return <AuthProvider><Routes config={config} lang={lang} setLang={setLang} /></AuthProvider>;
}
