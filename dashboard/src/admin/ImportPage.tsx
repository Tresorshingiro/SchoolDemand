import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, CheckCircle2, ChevronRight, Download, FileSpreadsheet, XCircle } from 'lucide-react';
import { sendJson } from '../api';
import { fmt } from '../data';
import {
  BUSY, STATUS_LABEL, fileUrl, getImport, importAction, issuesUrl, type ImportDetail, type LevelChange, type Problem,
} from './api';
import { StatusPill } from './HistoryPage';
import { Alert, PageHeader, Panel, StatCard, btn, td, th } from './ui';

const when = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });

function Problems({ title, items, tone }: { title: string; items: Problem[]; tone: 'error' | 'warning' }) {
  if (!items.length) return null;
  const color = tone === 'error' ? 'var(--deficit)' : '#d4830b';
  const Icon = tone === 'error' ? XCircle : AlertTriangle;
  return (
    <Panel className="overflow-hidden">
      <h2 className="flex items-center gap-2 border-b border-line px-4 py-3 text-[14px] font-semibold text-ink">
        <Icon size={16} style={{ color }} aria-hidden /> {title}
        <span className="rounded-full px-2 text-[12px] font-medium" style={{ color, background: `color-mix(in srgb, ${color} 12%, transparent)` }}>
          {items.length}
        </span>
      </h2>
      <div className="divide-y divide-[var(--line)]">
        {items.map((p, i) => {
          const cols = p.rows.length ? Object.keys(p.rows[0]) : [];
          return (
            <details key={`${p.code}-${i}`} open={tone === 'error'} className="group px-4 py-3">
              <summary className="flex cursor-pointer list-none items-center gap-2 text-[13px] text-ink">
                <ChevronRight size={14} className="text-muted transition group-open:rotate-90" aria-hidden />
                <span className="flex-1">{p.message}</span>
                <span className="text-[12px] tabular-nums text-muted">{fmt(p.count)}</span>
              </summary>
              {cols.length > 0 && (
                <div className="mt-3 overflow-x-auto rounded-lg border border-line">
                  <table className="w-full text-[12px]">
                    <thead className="bg-page">
                      <tr>{cols.map((c) => <th key={c} className="px-3 py-2 text-left font-medium text-muted">{c}</th>)}</tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--line)]">
                      {p.rows.map((r, k) => (
                        <tr key={k}>{cols.map((c) => <td key={c} className="px-3 py-1.5 text-ink2">{String(r[c] ?? '')}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                  {p.count > p.rows.length && (
                    <p className="border-t border-line bg-page px-3 py-1.5 text-[11px] text-muted">First {p.rows.length} of {fmt(p.count)} — the CSV has them all.</p>
                  )}
                </div>
              )}
            </details>
          );
        })}
      </div>
    </Panel>
  );
}

const pctChange = ([a, b]: [number, number]) => (a ? `${b >= a ? '+' : ''}${(((b - a) / a) * 100).toFixed(1)}%` : '');

function Changes({ d }: { d: ImportDetail }) {
  const c = d.report?.changes;
  if (!c) return null;
  const cols: [keyof LevelChange, string][] = [['students', 'Students'], ['class_groups', 'Class groups'], ['rooms', 'Rooms'],
    ['required', 'Required'], ['gap', 'Gap']];
  return (
    <Panel className="overflow-hidden">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-[14px] font-semibold text-ink">Changes against {c.replaces ? 'the live ' : ''}{c.against}</h2>
        <p className="mt-0.5 text-[12px] text-muted">
          Schools {fmt(c.schools[0])} → {fmt(c.schools[1])} · {fmt(c.schools_added)} added · {fmt(c.schools_removed)} removed
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-page">
            <tr><th className={th}>Level</th>{cols.map(([, l]) => <th key={l} className={`${th} text-right`}>{l}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-[var(--line)]">
            {c.levels.map((row) => (
              <tr key={row.level}>
                <td className={`${td} font-medium text-ink`}>{row.level}</td>
                {cols.map(([k]) => {
                  const v = row[k] as [number, number];
                  return (
                    <td key={k} className={`${td} text-right tabular-nums`}>
                      <span className="text-muted">{fmt(v[0])} →</span> <span className="text-ink">{fmt(v[1])}</span>
                      {k !== 'gap' && <span className="ml-1.5 text-[11px] text-muted">{pctChange(v)}</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

/** One import: progress, the check report, and what can be done with it. */
export default function ImportPage() {
  const id = Number(useParams().id);
  const [d, setD] = useState<ImportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getImport(id).then(setD).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [id]);
  useEffect(load, [load]);
  useEffect(() => {
    if (!d || !BUSY.includes(d.status)) return;
    const t = window.setTimeout(load, 1500);
    return () => window.clearTimeout(t);
  }, [d, load]);

  const run = async (action: 'publish' | 'discard' | 'recheck' | 'withdraw', confirmText?: string) => {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setError(null);
    try {
      setD(await importAction(id, action));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      load();
    } finally {
      setBusy(false);
    }
  };
  const reloadData = async () => {
    setBusy(true);
    try {
      await sendJson('POST', '/admin/reload');
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!d) return <p className="text-[13px] text-muted">{error ?? 'Loading…'}</p>;
  const report = d.report;
  const working = BUSY.includes(d.status);
  const problems = report ? report.errors.length + report.warnings.length : 0;
  const summary = report?.summary ?? {};
  const figures = Object.entries(summary).filter(([, v]) => typeof v === 'number') as [string, number][];
  const actions = !working && (d.can_publish || ['ready', 'failed'].includes(d.status) || (d.is_live && d.kind !== 'catchment'));

  return (
    <div className="pb-4">
      <PageHeader
        above={<Link to="/admin/data" className="inline-flex items-center gap-1 text-[12px] text-muted hover:text-ink"><ArrowLeft size={13} /> Data sources</Link>}
        title={<span className="flex items-center gap-2"><FileSpreadsheet size={20} className="text-muted" aria-hidden />{d.file_name}</span>}
        badge={<StatusPill status={d.status} />}
        description={
          <>
            {d.label}{d.academic_year ? ` · school year ${d.academic_year}` : ''} · uploaded by {d.uploaded_by ?? 'the command line'},{' '}
            {when.format(new Date(d.uploaded_at))}
            {d.published_at ? ` · published by ${d.published_by ?? 'the command line'}, ${when.format(new Date(d.published_at))}` : ''}
          </>
        }
        actions={<a href={fileUrl(d.id)} className={btn.secondary}><Download size={15} aria-hidden /> Download file</a>} />

      {working && (
        <Panel className="mb-4 p-4" >
          <div className="flex items-center justify-between text-[13px] text-ink2" role="status">
            <span>{STATUS_LABEL[d.status]}</span><span className="tabular-nums text-muted">{d.progress}%</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--line)]">
            <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${Math.max(d.progress, 5)}%` }} />
          </div>
        </Panel>
      )}
      {d.error && (
        <Alert tone="error">
          {d.error}
          {d.status === 'published' && (
            <button type="button" className={`${btn.secondary} ml-3`} disabled={busy} onClick={() => void reloadData()}>Reload data</button>
          )}
        </Alert>
      )}
      {error && <Alert tone="error">{error}</Alert>}

      {report && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {figures.slice(0, 2).map(([k, v]) => (
              <StatCard key={k} label={k.replace(/_/g, ' ').replace(/^./, (s) => s.toUpperCase())} value={fmt(v)} tone="grey" />
            ))}
            <StatCard label="Errors" value={report.errors.length} tone={report.errors.length ? 'red' : 'green'}
              icon={report.errors.length ? <XCircle size={18} /> : <CheckCircle2 size={18} />}
              hint={report.errors.length ? 'They block publishing' : 'Ready to publish'} />
            <StatCard label="Warnings" value={report.warnings.length} tone={report.warnings.length ? 'amber' : 'green'}
              icon={<AlertTriangle size={18} />} hint="Read them before publishing" />
          </div>
          {problems > 0 && (
            <a href={issuesUrl(d.id)} className="inline-flex items-center gap-1.5 text-[13px] font-medium text-accent hover:underline">
              <Download size={14} aria-hidden /> Download every problem row (CSV)
            </a>
          )}
          <Problems title="Errors" items={report.errors} tone="error" />
          <Problems title="Warnings" items={report.warnings} tone="warning" />
          <Changes d={d} />
        </div>
      )}

      {actions && (
        <div className="sticky bottom-0 z-20 -mx-4 mt-6 border-t border-line bg-surface/95 px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8 lg:-mx-10 lg:px-10">
          <div className="flex flex-wrap items-center gap-2">
            <p className="mr-auto text-[13px] text-ink2">
              {d.can_publish ? d.consequence
                : report && report.errors.length > 0 && d.status === 'ready' ? 'Fix the errors in the file and upload it again.'
                : d.is_live ? 'This data is live on the site.' : ''}
            </p>
            {['ready', 'failed'].includes(d.status) && !d.is_live && (
              <button type="button" className={btn.secondary} disabled={busy} onClick={() => void run('discard', 'Discard this import?')}>Discard</button>
            )}
            {d.status === 'failed' && <button type="button" className={btn.secondary} disabled={busy} onClick={() => void run('recheck')}>Check again</button>}
            {d.is_live && d.kind !== 'catchment' && (
              <button type="button" className={btn.danger} disabled={busy}
                onClick={() => void run('withdraw', `Withdraw this ${d.kind === 'school_data' ? `${d.academic_year} school data` : 'NISR data'} from the site?`)}>
                Withdraw
              </button>
            )}
            {d.status === 'published' && <Link to="/dashboard" className={btn.secondary}>Open the dashboard</Link>}
            {d.can_publish && (
              <button type="button" disabled={busy} className={btn.primary}
                onClick={() => void run('publish', `${d.status === 'ready' ? 'Publish' : 'Publish again'}? ${d.consequence ?? ''}`)}>
                {d.status === 'ready' ? 'Publish' : 'Publish again'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
