import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { usePrinting } from './print';

export type Mode = 'light' | 'dark';

/**
 * Colour roles. Categorical slots and ramps follow the dataviz reference palette;
 * light and dark steps are chosen separately, not flipped.
 */
export const COLORS = {
  light: {
    surface: '#fcfcfb',
    ink: '#0b0b0b',
    ink2: '#52514e',
    muted: '#898781',
    grid: '#e1e0d9',
    axis: '#c3c2b7',
    available: '#2a78d6', // categorical slot 1
    required: '#eb6834', // categorical slot 2
    doubleShift: '#4a3aa7', // categorical slot 7 — used only for double shift
    deficit: '#e34948',
  },
  dark: {
    surface: '#1a1a19',
    ink: '#ffffff',
    ink2: '#c3c2b7',
    muted: '#898781',
    grid: '#2c2c2a',
    axis: '#383835',
    available: '#3987e5',
    required: '#d95926',
    doubleShift: '#9085e9',
    deficit: '#e66767',
  },
} as const;

export type Palette = (typeof COLORS)[Mode];

/**
 * Diverging classes for the classroom gap (red = deficit, grey = exact fit, blue = surplus).
 * On the dark basemap the strongest classes step lighter so they stay the most salient.
 */
export interface GapClass {
  min: number;
  max: number;
  label: string;
  light: string;
  dark: string;
}

export const GAP_CLASSES: GapClass[] = [
  { min: -100000, max: -10, label: '10+ short', light: '#a3201f', dark: '#ff8a85' },
  { min: -9, max: -4, label: '4–9 short', light: '#e34948', dark: '#e34948' },
  { min: -3, max: -1, label: '1–3 short', light: '#f29b97', dark: '#9e3b39' },
  { min: 0, max: 0, label: 'Exact fit', light: '#a3a19a', dark: '#6b6a64' },
  { min: 1, max: 3, label: '1–3 spare', light: '#86b6ef', dark: '#1c5cab' },
  { min: 4, max: 9, label: '4–9 spare', light: '#2a78d6', dark: '#3987e5' },
  { min: 10, max: 100000, label: '10+ spare', light: '#184f95', dark: '#86b6ef' },
];

/**
 * Ordinal blue ramp for the grades of a level (first grade -> last grade). Six steps interpolated in OKLab
 * between ramp steps 250 and 700 (light) / 600 and 100 (dark) so that P1-P6 stay visibly distinct;
 * validated with the dataviz validator (--ordinal) in both modes. On dark the first grade sits nearest the surface.
 */
export const GRADE_RAMP = {
  light: ['#86b6ef', '#6d9bd3', '#5480b8', '#3c679e', '#254e84', '#0d366b'],
  dark: ['#184f95', '#3d6caa', '#6089be', '#84a6d3', '#a8c4e7', '#cde2fb'],
} as const;

/** `n` evenly spaced steps of the grade ramp (a level has 3 to 6 grades). */
export function gradeColors(n: number, mode: Mode): string[] {
  const ramp = GRADE_RAMP[mode];
  if (n <= 1) return [ramp[3]];
  return Array.from({ length: n }, (_, i) => ramp[Math.round((i * (ramp.length - 1)) / (n - 1))]);
}

export const STATUS_COLORS = {
  light: { Deficit: '#e34948', 'Exact fit': '#a3a19a', Surplus: '#2a78d6' },
  dark: { Deficit: '#e66767', 'Exact fit': '#6b6a64', Surplus: '#3987e5' },
} as const;

const STORAGE_KEY = 'classroom-dashboard-theme';

function systemMode(): Mode {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function storedMode(): Mode | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null;
  }
}

interface ThemeState {
  mode: Mode;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

/**
 * Theme follows the OS unless the viewer picks one; the choice is stamped on <html data-theme> and shared by every
 * page (landing, sign-in, dashboard). A printed report is always light.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [chosen, setMode] = useState<Mode>(() => storedMode() ?? systemMode());
  const printing = usePrinting();
  const mode: Mode = printing ? 'light' : chosen;

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
  }, [mode]);

  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!mq) return;
    const onChange = () => {
      if (!storedMode()) setMode(systemMode());
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const toggle = useCallback(() => {
    setMode((m) => {
      const next = m === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* storage unavailable — choice lasts for this visit only */
      }
      return next;
    });
  }, []);

  const value = useMemo(() => ({ mode, toggle }), [mode, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme outside ThemeProvider');
  return ctx;
}

/** Light / dark switch (a sun or a moon), used in the dashboard and the landing page headers. */
export function ThemeToggle({ className = '' }: { className?: string }) {
  const { mode, toggle } = useTheme();
  return (
    <button type="button" onClick={toggle} title={mode === 'dark' ? 'Light theme' : 'Dark theme'}
      aria-label={`Switch to ${mode === 'dark' ? 'light' : 'dark'} theme`} className={className}>
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {mode === 'dark'
          ? <path d="M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" />
          : <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8" />}
      </svg>
    </button>
  );
}
