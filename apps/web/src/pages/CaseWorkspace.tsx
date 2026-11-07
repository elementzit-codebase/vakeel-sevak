import { useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { Button, StatusTag } from '../components';
import { CaseTasks, Documents, Hearings, Messages, Overview, type Detail } from './CaseTabs';
import { Empty, PageHead, Tabs, fmtDate, useData } from '../ui';

export function CaseWorkspace({ id, onBack }: { id: string; onBack: () => void }) {
  const { can } = useAuth();
  const { data, error, reload } = useData<Detail & { next_hearing: string | null }>(`/cases/${id}`);
  const [tab, setTab] = useState('overview');
  if (error) return <><Button kind="text" onClick={onBack}>← Cases</Button><Empty>{error}</Empty></>;
  if (!data) return null;
  const tabs = [
    { key: 'overview', label: 'Overview' }, { key: 'hearings', label: 'Hearings' }, { key: 'tasks', label: 'Tasks' },
    ...(can('docs.read') ? [{ key: 'docs', label: 'Documents' }] : []),
    ...(can('records.write') ? [{ key: 'messages', label: 'Client' }] : []),
  ];
  return (
    <>
      <Button kind="text" onClick={onBack}>← Cases</Button>
      <PageHead title={data.title} help={`${data.case_number} · ${data.court}`}
        actions={<><StatusTag>{data.stage}</StatusTag><StatusTag tone="caution">Next: {fmtDate(data.next_hearing)}</StatusTag></>} />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === 'overview' && <Overview d={data} reload={reload} />}
      {tab === 'hearings' && <Hearings d={data} reload={reload} />}
      {tab === 'tasks' && <CaseTasks caseId={id} />}
      {tab === 'docs' && <Documents caseId={id} />}
      {tab === 'messages' && <Messages caseId={id} />}
    </>
  );
}
