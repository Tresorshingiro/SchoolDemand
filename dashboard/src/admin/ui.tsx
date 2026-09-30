/** Shared building blocks of the admin portal, so every page has the same scale and finish. */
import type { ReactNode } from 'react';

export const btn = {
  primary: 'inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-accent px-3.5 text-[13px] font-medium text-white shadow-sm transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50',
  secondary: 'inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-[13px] font-medium text-ink2 shadow-sm transition hover:bg-[var(--line)] hover:text-ink disabled:cursor-not-allowed disabled:opacity-50',
  danger: 'inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-[color-mix(in_srgb,var(--deficit)_35%,transparent)] bg-surface px-3 text-[13px] font-medium text-[var(--deficit)] shadow-sm transition hover:bg-[var(--deficit-soft)] disabled:opacity-50',
  icon: 'grid h-8 w-8 place-items-center rounded-lg text-ink2 transition hover:bg-[var(--line)] hover:text-ink',
};

/** Text inputs and selects. */
export const field = 'h-9 rounded-lg border border-line bg-surface px-3 text-[13px] text-ink shadow-sm outline-none transition placeholder:text-muted focus:border-[var(--accent)] focus:ring-4 focus:ring-[var(--accent-soft)]';

/** Table header and body cells. */
export const th = 'px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-muted';
export const td = 'px-4 py-3 text-[13px] text-ink2';

/** A card with the portal's border, radius and shadow. */
export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-surface shadow-sm ${className}`}>{children}</div>;
}

/** Title, one-line description and the page's main actions. */
export function PageHeader({ title, description, actions, above, badge }: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  above?: ReactNode; // e.g. a back link
  badge?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
      <div className="min-w-0">
        {above && <div className="mb-2">{above}</div>}
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
          {badge}
        </div>
        {description && <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export type Tone = 'green' | 'amber' | 'red' | 'blue' | 'grey';
// Mid-tone hues that read on the light and the dark surface; the fill is the same hue, faint
const TONE: Record<Tone, string> = {
  green: '#1f9d55',
  amber: '#d4830b',
  red: 'var(--deficit)',
  blue: 'var(--accent)',
  grey: 'var(--muted)',
};

/** A small coloured status label. */
export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  const c = TONE[tone];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11.5px] font-medium"
      style={{ color: c, background: `color-mix(in srgb, ${c} 13%, transparent)` }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: c }} aria-hidden />
      {children}
    </span>
  );
}

const AVATAR_HUES = ['#2a78d6', '#1f9d55', '#d4830b', '#8b5cf6', '#db2777', '#0891b2', '#65a30d'];

export function initials(name: string): string {
  const words = name.replace(/@.*/, '').split(/[\s._-]+/).filter(Boolean);
  return ((words[0]?.[0] ?? '?') + (words.length > 1 ? words[words.length - 1][0] : '')).toUpperCase();
}

/** Initials in a circle, the same colour for the same name. */
export function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const c = AVATAR_HUES[h % AVATAR_HUES.length];
  return (
    <span className="grid shrink-0 place-items-center rounded-full font-semibold" aria-hidden
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38), color: c,
        background: `color-mix(in srgb, ${c} 15%, transparent)` }}>
      {initials(name)}
    </span>
  );
}

/** A figure with its label, for the summary rows at the top of a page. */
export function StatCard({ label, value, hint, icon, tone = 'blue' }: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
}) {
  const c = TONE[tone];
  return (
    <Panel className="flex items-start gap-3 p-4">
      {icon && (
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg"
          style={{ color: c, background: `color-mix(in srgb, ${c} 12%, transparent)` }}>
          {icon}
        </span>
      )}
      <div className="min-w-0">
        <div className="text-[12px] font-medium text-muted">{label}</div>
        <div className="mt-0.5 text-2xl font-semibold tracking-tight text-ink">{value}</div>
        {hint && <div className="mt-0.5 text-[12px] text-muted">{hint}</div>}
      </div>
    </Panel>
  );
}

/** Shown where a list has nothing to show. */
export function EmptyState({ icon, title, text }: { icon: ReactNode; title: string; text?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <span className="grid h-10 w-10 place-items-center rounded-full bg-[var(--line)] text-muted">{icon}</span>
      <p className="text-[13px] font-medium text-ink">{title}</p>
      {text && <p className="max-w-sm text-[12px] text-muted">{text}</p>}
    </div>
  );
}

/** An error or notice line. */
export function Alert({ tone, children }: { tone: 'error' | 'info'; children: ReactNode }) {
  const c = tone === 'error' ? 'var(--deficit)' : 'var(--accent)';
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className="mb-4 rounded-lg border px-3.5 py-2.5 text-[13px] text-ink"
      style={{ borderColor: `color-mix(in srgb, ${c} 35%, transparent)`, background: `color-mix(in srgb, ${c} 8%, transparent)` }}>
      {children}
    </div>
  );
}
