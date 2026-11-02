import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, X } from 'lucide-react';
import { KIND_LABEL, YEAR_KINDS, uploadFile, type DataKind } from './api';
import { btn as buttons, field } from './ui';

const btn = buttons.secondary;
const NETWORK_FILE = { pattern: /\.osm\.pbf$/i, wrong: 'Upload the OpenStreetMap extract, an .osm.pbf file.', hint: '.osm.pbf', accept: '.pbf', mb: 200 };
const TABLE_FILE = { pattern: /\.(xlsx|csv)$/i, wrong: 'Upload an .xlsx or .csv file.', hint: '.xlsx or .csv', accept: '.xlsx,.csv', mb: 50 };

/** Side panel: choose a file (and the school year for school data), upload it, then open its check. */
export default function UploadPanel({ kind, suggestedYear, onClose }: {
  kind: DataKind;
  suggestedYear: number;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [year, setYear] = useState(String(suggestedYear));
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const rule = kind === 'walking_network' ? NETWORK_FILE : TABLE_FILE;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (!file) return setError('Choose a file.');
    if (!rule.pattern.test(file.name)) return setError(rule.wrong);
    if (file.size > rule.mb * 1024 * 1024) return setError(`The file is larger than ${rule.mb} MB.`);
    setBusy(true);
    try {
      const run = await uploadFile(kind, file, YEAR_KINDS.includes(kind) ? Number(year) : undefined);
      navigate(`/admin/data/imports/${run.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-[2px]" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form onSubmit={submit} noValidate role="dialog" aria-label={`Upload ${KIND_LABEL[kind]}`}
        className="flex h-full w-full max-w-md flex-col gap-5 overflow-y-auto border-l border-line bg-surface p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b border-line pb-4">
          <h2 className="text-[16px] font-semibold text-ink">Upload {KIND_LABEL[kind]}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className={buttons.icon}>
            <X size={16} aria-hidden />
          </button>
        </div>
        <p className="text-[13px] leading-relaxed text-muted">
          The file is checked first; nothing changes on the site until you publish it from the report.
        </p>
        <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-line bg-page px-4 py-8 text-center transition hover:border-[var(--accent)]">
          <UploadCloud size={28} className="text-accent" aria-hidden />
          <span className="text-[13px] font-medium text-ink">{file ? file.name : 'Choose a file'}</span>
          <span className="text-[12px] text-muted">{rule.hint}, up to {rule.mb} MB</span>
          <input type="file" accept={rule.accept} onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="sr-only" />
        </label>
        {YEAR_KINDS.includes(kind) && (
          <label className="text-[13px] font-medium text-ink2">School year of the file
            <input type="number" min={2000} max={2100} value={year} onChange={(e) => setYear(e.target.value)}
              className={`mt-1.5 block w-32 ${field}`} />
          </label>
        )}
        {error && <p className="text-[13px] text-[var(--deficit)]" role="alert">{error}</p>}
        <div className="mt-auto flex justify-end gap-2 border-t border-line pt-4">
          <button type="button" className={btn} onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy}
            className={buttons.primary}>
            {busy ? 'Uploading…' : 'Upload and check'}
          </button>
        </div>
      </form>
    </div>
  );
}
