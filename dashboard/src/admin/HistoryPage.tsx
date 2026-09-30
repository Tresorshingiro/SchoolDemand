import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, History } from 'lucide-react';
import { KIND_LABEL, STATUS_LABEL, listImports, type DataKind, type ImportRun } from './api';
import { KIND_INFO } from './DataSourcesPage';
import { Alert, EmptyState, PageHeader, Panel, Pill, field, td, th, type Tone } from './ui';

const when = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const STATUS_TONE: Record<string, Tone> = {
  published: 'green', ready: 'blue', uploaded: 'blue', checking: 'blue', publishing: 'blue', withdrawing: 'blue',
  failed: 'red', superseded: 'grey', discarded: 'grey', withdrawn: 'grey',
};

/** An import's status as a coloured label. */
export function StatusPill({ status }: { status: string }) {
  return <Pill tone={STATUS_TONE[status] ?? 'grey'}>{STATUS_LABEL[status] ?? status}</Pill>;
}

/** Who and when; loads from the command line have no user. */
const byWhen = (who: string | null, at: string) => (
  <>
    <div className="text-ink">{who ?? 'Command line'}</div>
    <div className="text-[12px] text-muted">{when.format(new Date(at))}</div>
  </>
);

/** Every import, newest first. */
export default function HistoryPage() {
  const [kind, setKind] = useState<DataKind | ''>('');
  const [rows, setRows] = useState<ImportRun[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listImports(kind || undefined).then(setRows).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoaded(true));
  }, [kind]);

  return (
    <div>
      <PageHeader title="Import history"
        above={<Link to="/admin/data" className="inline-flex items-center gap-1 text-[12px] text-muted hover:text-ink"><ArrowLeft size={13} /> Data sources</Link>}
        description="Open an import to read its report, download its file, or publish it again."
        actions={
          <select aria-label="Kind" className={field} value={kind} onChange={(e) => setKind(e.target.value as DataKind | '')}>
            <option value="">All kinds</option>
            {(Object.keys(KIND_LABEL) as DataKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        } />
      {error && <Alert tone="error">{error}</Alert>}
      <Panel className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-page">
              <tr>
                <th className={th}>File</th><th className={th}>Kind</th><th className={th}>Year</th>
                <th className={th}>Status</th><th className={th}>Uploaded</th><th className={th}>Published</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--line)]">
              {rows.map((r) => {
                const Icon = KIND_INFO[r.kind].icon;
                return (
                  <tr key={r.id} className="transition hover:bg-page">
                    <td className={td}>
                      <Link to={`/admin/data/imports/${r.id}`} className="font-medium text-accent hover:underline">{r.file_name}</Link>
                    </td>
                    <td className={td}>
                      <span className="inline-flex items-center gap-2 whitespace-nowrap"><Icon size={15} className="text-muted" aria-hidden />{KIND_LABEL[r.kind]}</span>
                    </td>
                    <td className={`${td} tabular-nums`}>{r.academic_year ?? <span className="text-muted">—</span>}</td>
                    <td className={td}><StatusPill status={r.status} /></td>
                    <td className={td}>{byWhen(r.uploaded_by, r.uploaded_at)}</td>
                    <td className={td}>{r.published_at ? byWhen(r.published_by, r.published_at) : <span className="text-muted">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {loaded && !rows.length && <EmptyState icon={<History size={18} />} title="No import yet" />}
        </div>
      </Panel>
    </div>
  );
}
