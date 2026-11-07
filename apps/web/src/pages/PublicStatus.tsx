import { useEffect, useState } from 'react';
import { Card } from '../components';
import { fmtDate } from '../ui';

type S = { title: string; case_number: string; court: string; stage: string; next_hearing: string | null; office: string };

/** Opened from a link the advocate shares. No sign-in, read only, shows the stage and next date and nothing else. */
export function PublicStatus({ token }: { token: string }) {
  const [s, setS] = useState<S | null>(null);
  const [bad, setBad] = useState(false);
  useEffect(() => {
    fetch(`/api/public/status/${encodeURIComponent(token)}`).then(async (r) => (r.ok ? setS(await r.json()) : setBad(true))).catch(() => setBad(true));
  }, [token]);
  return (
    <main className="vs-page">
      {bad && <Card><h1>This link is not valid</h1><p>It may have expired. Please contact your advocate for a new one.</p></Card>}
      {s && (
        <Card>
          <div className="vs-help">{s.office}</div>
          <h1>{s.title}</h1>
          <p>{s.case_number} · {s.court}</p>
          <p><strong>Stage:</strong> {s.stage}</p>
          <p><strong>Next hearing:</strong> {s.next_hearing ? fmtDate(s.next_hearing) : 'not fixed yet'}</p>
        </Card>
      )}
    </main>
  );
}
