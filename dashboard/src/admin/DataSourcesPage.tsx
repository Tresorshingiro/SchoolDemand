import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, FileSpreadsheet, History, MapPin, School, Upload, Users2, type LucideIcon } from 'lucide-react';
import { listSources, templateUrl, type DataKind, type ImportRun, type SourceCard } from './api';
import UploadPanel from './UploadPanel';
import { Alert, PageHeader, Panel, Pill, btn } from './ui';

const day = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

export const KIND_INFO: Record<DataKind, { icon: LucideIcon; text: string }> = {
  school_data: { icon: School, text: 'Schools, rooms and class groups of a school year. The newest year is the base of the projection.' },
  catchment: { icon: MapPin, text: "Children aged 3 in each pre-primary school's catchment area, per year." },
  nisr_population: { icon: Users2, text: 'Children aged 3 per district and year: the totals of the default N1 plan.' },
};

function LiveRow({ run }: { run: ImportRun }) {
  return (
    <Link to={`/admin/data/imports/${run.id}`}
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-line bg-page px-3 py-2.5 transition hover:border-[color-mix(in_srgb,var(--accent)_40%,transparent)]">
      <FileSpreadsheet size={16} className="text-muted" aria-hidden />
      {run.academic_year && <span className="text-[13px] font-semibold text-ink">{run.academic_year}</span>}
      <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{run.file_name}</span>
      <span className="text-[12px] text-muted">
        {run.published_by ?? 'Command line'}{run.published_at ? ` · ${day.format(new Date(run.published_at))}` : ''}
      </span>
      <Pill tone="green">Live</Pill>
    </Link>
  );
}

/** The live data of each kind, with Upload and Template. */
export default function DataSourcesPage() {
  const [cards, setCards] = useState<SourceCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [upload, setUpload] = useState<DataKind | null>(null);

  useEffect(() => {
    listSources().then(setCards).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  const newestYear = Math.max(0, ...(cards.find((c) => c.kind === 'school_data')?.live ?? []).map((r) => r.academic_year ?? 0));

  return (
    <div>
      <PageHeader title="Data sources"
        description="Upload a new file, read its check, then publish it. Nothing changes on the site until you publish, and every import is kept in the history."
        actions={<Link to="/admin/data/history" className={btn.secondary}><History size={15} aria-hidden /> Import history</Link>} />
      {error && <Alert tone="error">{error}</Alert>}
      <div className="grid gap-4">
        {cards.map((c) => {
          const Icon = KIND_INFO[c.kind].icon;
          return (
            <Panel key={c.kind} className="p-5">
              <div className="flex flex-wrap items-start gap-4">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[var(--accent-soft)] text-accent">
                  <Icon size={20} aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className="text-[15px] font-semibold text-ink">{c.label}</h2>
                  <p className="mt-0.5 text-[13px] text-muted">{KIND_INFO[c.kind].text}</p>
                </div>
                <div className="flex gap-2">
                  <a className={btn.secondary} href={templateUrl(c.kind)}>
                    <Download size={15} aria-hidden /> Template
                  </a>
                  <button type="button" className={btn.primary} onClick={() => setUpload(c.kind)}>
                    <Upload size={15} aria-hidden /> Upload
                  </button>
                </div>
              </div>
              <div className="mt-4 space-y-2 sm:pl-14">
                {c.live.length ? c.live.map((r) => <LiveRow key={r.id} run={r} />) : (
                  <p className="rounded-lg border border-dashed border-line px-3 py-2.5 text-[13px] text-muted">
                    {c.kind === 'nisr_population' ? 'Nothing published: the default N1 plan uses the catchment totals.' : 'Nothing published yet.'}
                  </p>
                )}
                {c.connector && <p className="text-[12px] text-muted">MINEDUC API connector: {c.connector}.</p>}
              </div>
            </Panel>
          );
        })}
      </div>
      {upload && (
        <UploadPanel kind={upload} suggestedYear={newestYear ? newestYear + 1 : new Date().getFullYear()}
          onClose={() => setUpload(null)} />
      )}
    </div>
  );
}
