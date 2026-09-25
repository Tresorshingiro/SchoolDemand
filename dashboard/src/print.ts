/**
 * "Download PDF": lay the page out for A4 landscape, let components prepare (the map swaps its WebGL
 * canvas for a screenshot, which the browser cannot print), then open the print dialog, where the
 * viewer picks "Save as PDF". While `printing` is true the app renders in the light theme at the
 * printable width, and components can show print-only content (see usePrinting).
 */
import { useSyncExternalStore } from 'react';

type Prepare = () => Promise<void>;

const preparers = new Set<Prepare>();
const listeners = new Set<() => void>();
let printing = false;

function setPrinting(value: boolean) {
  printing = value;
  document.documentElement.classList.toggle('printing', value);
  listeners.forEach((l) => l());
}

/** Register work to finish before the print dialog opens; returns the unregister function. */
export function onBeforePrint(fn: Prepare): () => void {
  preparers.add(fn);
  return () => {
    preparers.delete(fn);
  };
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** True while the report is being laid out and printed. */
export function usePrinting(): boolean {
  return useSyncExternalStore(subscribe, () => printing);
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const withTimeout = (p: Promise<void>, ms: number) => Promise.race([p, wait(ms)]);

/** Open the print dialog for the current view. `filename` becomes the suggested PDF name. */
export async function printReport(filename: string): Promise<void> {
  if (printing) return;
  const title = document.title;
  setPrinting(true);
  document.title = filename;
  try {
    await wait(700); // re-render in the light theme and let the charts resize to the page width
    await Promise.all([...preparers].map((fn) => withTimeout(fn().catch(() => undefined), 10000)));
    await wait(150); // let React render what the preparers set (e.g. the map screenshot)
  } catch {
    /* print what we have */
  }
  const done = () => {
    window.removeEventListener('afterprint', done);
    document.title = title;
    setPrinting(false);
  };
  window.addEventListener('afterprint', done);
  window.print();
}
