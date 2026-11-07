import { useState } from 'react';
import { AIDraft, Button, Card, DataTable, Input, StatusTag, TabBar } from '../components';
import { languageNames, t } from '../i18n';
import type { AppConfig } from '../config';

const rows = [
  { id: '1', title: 'Sharma v. State of Karnataka', no: 'O.S. 1234/2024', tone: 'caution' as const, status: 'Today' },
  { id: '2', title: 'Iyer v. Iyer', no: 'M.C. 77/2024', tone: 'alert' as const, status: 'Record to approve' },
  { id: '3', title: 'State v. Nair', no: 'S.C. 410/2025', tone: 'neutral' as const, status: 'Scheduled' },
];

export function Gallery({ config, lang, setLang }: { config: AppConfig; lang: string; setLang: (l: string) => void }) {
  const [tab, setTab] = useState('today');
  return (
    <main className="vs-page">
      <header className="vs-row" style={{ justifyContent: 'space-between' }}>
        <div>
          <h1>{config.product_name}</h1>
          <div className="vs-help">Foundation build · component gallery</div>
        </div>
        <div className="vs-row">
          {config.languages.map((l) => (
            <Button key={l} kind={l === lang ? 'primary' : 'secondary'} onClick={() => setLang(l)}>{languageNames[l] ?? l}</Button>
          ))}
        </div>
      </header>
      <Card>
        <div className="vs-row">
          <Button>{t(lang, 'recordHearing')}</Button>
          <Button kind="secondary">{t(lang, 'cases')}</Button>
          <Button kind="text">Cancel</Button>
          <Button disabled>Disabled</Button>
        </div>
      </Card>
      <Card>
        <div className="vs-row">
          <StatusTag tone="alert">Overdue</StatusTag>
          <StatusTag tone="caution">Today</StatusTag>
          <StatusTag tone="ok">Approved</StatusTag>
          <StatusTag>Scheduled</StatusTag>
        </div>
      </Card>
      <Card>
        <div style={{ display: 'grid', gap: 16, gridTemplateColumns: '1fr 1fr' }}>
          <Input label="Email" placeholder="name@yourchambers.in" type="email" />
          <Input label="Password" type="password" error="Enter your password" />
        </div>
      </Card>
      <AIDraft title="Hearing record" actions={<><Button>{t(lang, 'approve')}</Button><Button kind="secondary">Edit</Button></>}>
        Cross-examination of PW-2 was done in part. Next date 3 December 2026.
      </AIDraft>
      <DataTable
        rows={rows}
        rowKey={(r) => r.id}
        columns={[
          { header: 'Case', cell: (r) => <><strong>{r.title}</strong><div className="vs-help">{r.no}</div></> },
          { header: 'Status', cell: (r) => <StatusTag tone={r.tone}>{r.status}</StatusTag> },
        ]}
      />
      <TabBar
        active={tab}
        onChange={setTab}
        tabs={[
          { key: 'today', label: t(lang, 'today') },
          { key: 'cases', label: t(lang, 'cases') },
          { key: 'calendar', label: t(lang, 'calendar') },
          { key: 'assistant', label: t(lang, 'assistant') },
        ]}
      />
    </main>
  );
}
