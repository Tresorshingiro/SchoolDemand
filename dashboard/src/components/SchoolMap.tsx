import { useEffect, useMemo, useRef, useState } from 'react';
import esriConfig from '@arcgis/core/config';
import { version as arcgisVersion } from '@arcgis/core/kernel';
import ArcGISMap from '@arcgis/core/Map';
import MapView from '@arcgis/core/views/MapView';
import Basemap from '@arcgis/core/Basemap';
import TileLayer from '@arcgis/core/layers/TileLayer';
import OpenStreetMapLayer from '@arcgis/core/layers/OpenStreetMapLayer';
import GeoJSONLayer from '@arcgis/core/layers/GeoJSONLayer';
import ClassBreaksRenderer from '@arcgis/core/renderers/ClassBreaksRenderer';
import SimpleMarkerSymbol from '@arcgis/core/symbols/SimpleMarkerSymbol';
import Extent from '@arcgis/core/geometry/Extent';
import * as reactiveUtils from '@arcgis/core/core/reactiveUtils';
import type Graphic from '@arcgis/core/Graphic';
import '@arcgis/core/assets/esri/themes/light/main.css';

import { fmt, fmtGap, type SchoolLevel } from '../data';
import { COLORS, GAP_CLASSES, type Mode } from '../theme';
import { onBeforePrint, usePrinting } from '../print';

// Same setup as BTS ecofleet-web: with Vite, @arcgis/core must fetch its assets from the CDN.
esriConfig.assetsPath = `https://js.arcgis.com/${arcgisVersion}/@arcgis/core/assets`;
const ARCGIS_TOKEN = import.meta.env.VITE_ARCGIS_TOKEN as string | undefined;
if (ARCGIS_TOKEN) esriConfig.apiKey = ARCGIS_TOKEN;

const RWANDA_CENTER: [number, number] = [29.87, -1.94];
const SERVICES = 'https://services.arcgisonline.com/ArcGIS/rest/services';
const CANVAS = {
  light: `${SERVICES}/Canvas/World_Light_Gray_Base/MapServer`,
  dark: `${SERVICES}/Canvas/World_Dark_Gray_Base/MapServer`,
};
const IMAGERY = `${SERVICES}/World_Imagery/MapServer`;
const IMAGERY_LABELS = `${SERVICES}/Reference/World_Boundaries_and_Places/MapServer`;

export type BasemapKind = 'canvas' | 'satellite';
const BASEMAP_KEY = 'classroom-dashboard-basemap';

function storedBasemap(): BasemapKind {
  try {
    return localStorage.getItem(BASEMAP_KEY) === 'satellite' ? 'satellite' : 'canvas';
  } catch {
    return 'canvas';
  }
}

async function loadTiles(url: string): Promise<TileLayer> {
  const layer = new TileLayer({ url });
  await layer.load();
  return layer;
}

/**
 * Grey canvas or Esri World Imagery with boundary/place labels (both keyless, as in BTS).
 * Falls back imagery -> canvas -> OpenStreetMap.
 */
async function makeBasemap(mode: Mode, kind: BasemapKind): Promise<Basemap> {
  if (kind === 'satellite') {
    try {
      const imagery = await loadTiles(IMAGERY);
      const labels = await loadTiles(IMAGERY_LABELS).catch(() => null);
      return new Basemap({ baseLayers: [imagery], referenceLayers: labels ? [labels] : [], title: 'Satellite imagery' });
    } catch {
      /* fall through to the canvas */
    }
  }
  try {
    const canvas = await loadTiles(CANVAS[mode]);
    return new Basemap({ baseLayers: [canvas], title: mode === 'dark' ? 'Dark grey canvas' : 'Light grey canvas' });
  } catch {
    return new Basemap({ baseLayers: [new OpenStreetMapLayer()], title: 'OpenStreetMap' });
  }
}

function makeRenderer(mode: Mode, kind: BasemapKind): ClassBreaksRenderer {
  // On imagery a white ring keeps every class readable against fields, forest and roofs.
  const outline = kind === 'satellite' ? { color: '#ffffff', width: 1 } : { color: COLORS[mode].surface, width: 0.75 };
  return new ClassBreaksRenderer({
    field: 'gap',
    classBreakInfos: GAP_CLASSES.map((c) => ({
      minValue: c.min,
      maxValue: c.max,
      label: c.label,
      symbol: new SimpleMarkerSymbol({ style: 'circle', size: 7, color: c[mode], outline }),
    })),
    visualVariables: [
      {
        type: 'size',
        field: 'st',
        stops: [
          { value: 50, size: 3 },
          { value: 1000, size: 6 },
          { value: 4000, size: 12 },
        ],
      } as __esri.SizeVariableProperties,
    ],
  });
}

function toGeoJSON(rows: SchoolLevel[]) {
  return {
    type: 'FeatureCollection',
    features: rows
      .filter((r) => r.x !== null && r.y !== null)
      .map((r) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [r.x, r.y] },
        properties: { c: r.c, n: r.n, d: r.d, s: r.s, st: r.st, g: r.g, ds: r.ds, a: r.a, r: r.r, gap: r.gap },
      })),
  };
}

interface Hover {
  x: number;
  y: number;
  attrs: Record<string, number | string>;
}

interface Props {
  rows: SchoolLevel[];
  mode: Mode;
  selected: number | null;
  onSelect: (code: number) => void;
}

export default function SchoolMap({ rows, mode, selected, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<MapView | null>(null);
  const layerRef = useRef<GeoJSONLayer | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const [basemapName, setBasemapName] = useState('');
  const [kind, setKind] = useState<BasemapKind>(storedBasemap);
  // Printing: the WebGL canvas does not print, so a screenshot of the view stands in for it.
  const printing = usePrinting();
  const [shot, setShot] = useState<string | null>(null);
  const pendingRef = useRef<Promise<unknown>>(Promise.resolve()); // basemap / school layer still loading
  // Imagery is mid-dark in either theme, so dots use the saturated light-theme steps there.
  const dotMode: Mode = kind === 'satellite' ? 'light' : mode;

  const chooseKind = (next: BasemapKind) => {
    setKind(next);
    try {
      localStorage.setItem(BASEMAP_KEY, next);
    } catch {
      /* storage unavailable — choice lasts for this visit only */
    }
  };

  const mapped = useMemo(() => rows.filter((r) => r.x !== null).length, [rows]);

  // Create the view once.
  useEffect(() => {
    if (!containerRef.current) return;
    const map = new ArcGISMap();
    const view = new MapView({
      container: containerRef.current,
      map,
      center: RWANDA_CENTER,
      zoom: 8,
      constraints: { minZoom: 7, maxZoom: 18, rotationEnabled: false },
      ui: { components: ['zoom', 'attribution'] },
      popupEnabled: false,
    });
    viewRef.current = view;

    const hitLayer = async (event: __esri.ViewClickEvent | __esri.ViewPointerMoveEvent) => {
      const layer = layerRef.current;
      if (!layer) return null;
      const res = await view.hitTest(event, { include: [layer] });
      const hit = res.results.find((r): r is __esri.GraphicHit => r.type === 'graphic');
      return hit?.graphic ?? null;
    };

    const click = view.on('click', async (event) => {
      const g = await hitLayer(event);
      if (g) onSelectRef.current(Number(g.attributes.c));
    });

    let frame = 0;
    const move = view.on('pointer-move', (event) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(async () => {
        const g: Graphic | null = await hitLayer(event);
        if (containerRef.current) containerRef.current.style.cursor = g ? 'pointer' : '';
        setHover(g ? { x: event.x, y: event.y, attrs: g.attributes } : null);
      });
    });
    const leave = view.on('pointer-leave', () => setHover(null));

    view
      .when(() => setReady(true))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Map failed to load'));

    return () => {
      cancelAnimationFrame(frame);
      click.remove();
      move.remove();
      leave.remove();
      view.destroy();
      viewRef.current = null;
      layerRef.current = null;
    };
  }, []);

  // Basemap follows the theme and the Map / Satellite switch.
  useEffect(() => {
    let cancelled = false;
    pendingRef.current = makeBasemap(mode, kind).then((basemap) => {
      const view = viewRef.current;
      if (cancelled || !view?.map) return;
      view.map.basemap = basemap;
      setBasemapName(basemap.title);
    });
    return () => {
      cancelled = true;
    };
  }, [mode, kind]);

  // Rebuild the school layer whenever the filtered rows or theme change.
  useEffect(() => {
    const map = viewRef.current?.map;
    if (!map || !ready) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(toGeoJSON(rows))], { type: 'application/json' }));
    const layer = new GeoJSONLayer({
      url,
      title: 'Schools',
      outFields: ['*'],
      renderer: makeRenderer(dotMode, kind),
      orderBy: [{ field: 'gap', order: 'ascending' }], // largest deficits drawn on top
      popupEnabled: false,
    });
    map.add(layer);
    layerRef.current = layer;
    // The layer reads the blob while loading; release it only once that is done.
    let released = false;
    const release = () => {
      if (!released) URL.revokeObjectURL(url);
      released = true;
    };
    layer.when(release, release);
    pendingRef.current = Promise.all([pendingRef.current, layer.when().catch(() => undefined)]);
    return () => {
      map.remove(layer);
      if (layer.loaded) {
        release();
        layer.destroy();
      }
      // A layer still loading is released by its own when() callback once it settles.
    };
  }, [rows, dotMode, kind, ready]);

  useEffect(() => onBeforePrint(async () => {
    const view = viewRef.current;
    if (!view || !ready) return;
    await pendingRef.current;
    await reactiveUtils.whenOnce(() => !view.updating);
    const screenshot = await view.takeScreenshot({ format: 'png' });
    setShot(screenshot.dataUrl);
  }), [ready]);
  useEffect(() => {
    if (!printing) setShot(null);
  }, [printing]);

  // Zoom to the filtered schools (not on theme changes).
  useEffect(() => {
    const view = viewRef.current;
    if (!view || !ready) return;
    const pts = rows.filter((r) => r.x !== null && r.y !== null);
    if (!pts.length) return;
    const xs = pts.map((r) => r.x as number);
    const ys = pts.map((r) => r.y as number);
    const extent = new Extent({
      xmin: Math.min(...xs), xmax: Math.max(...xs), ymin: Math.min(...ys), ymax: Math.max(...ys),
      spatialReference: { wkid: 4326 },
    });
    view.goTo(extent.expand(1.25), { duration: 600 }).catch(() => undefined);
  }, [rows, ready]);

  // Highlight and fly to the selected school.
  useEffect(() => {
    const view = viewRef.current;
    const layer = layerRef.current;
    if (!view || !layer || selected === null) return;
    let handle: __esri.Handle | undefined;
    let cancelled = false;
    (async () => {
      const lv = await view.whenLayerView(layer);
      const { features } = await layer.queryFeatures({ where: `c = ${selected}`, returnGeometry: true, outFields: ['c'] });
      if (cancelled || !features.length) return;
      handle = lv.highlight(features[0]);
      view.goTo({ target: features[0].geometry, zoom: Math.max(view.zoom, 12) }, { duration: 600 }).catch(() => undefined);
    })().catch(() => undefined);
    return () => {
      cancelled = true;
      handle?.remove();
    };
  }, [selected, rows, dotMode, kind]);

  return (
    <div className="flex h-full flex-col">
      <div className="relative min-h-[360px] flex-1 overflow-hidden rounded-t-[10px]">
        <div ref={containerRef} className="absolute inset-0" aria-label="Map of schools coloured by classroom gap" />
        {printing && shot && (
          <img src={shot} alt="Map of schools coloured by classroom gap" className="absolute inset-0 z-20 h-full w-full object-cover" />
        )}
        {ready && (
          <div className="absolute right-3 top-3 z-10 flex gap-0.5 rounded-lg border border-line bg-surface p-0.5 shadow-md print:hidden"
            role="radiogroup" aria-label="Basemap">
            {(['canvas', 'satellite'] as const).map((k) => (
              <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => chooseKind(k)}
                className={`rounded-md px-3 py-1 text-xs font-medium ${kind === k ? 'bg-accent text-white' : 'text-ink2 hover:text-ink'}`}>
                {k === 'canvas' ? 'Map' : 'Satellite'}
              </button>
            ))}
          </div>
        )}
        {!ready && !error && (
          <div className="absolute inset-0 grid place-items-center text-sm text-muted">Loading map…</div>
        )}
        {error && (
          <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-ink2">
            Map could not load ({error}). Check access to js.arcgis.com — the charts and table still work.
          </div>
        )}
        {hover && (
          <div
            className="pointer-events-none absolute z-10 max-w-[260px] print:hidden rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-lg"
            style={{ left: Math.min(hover.x + 14, (containerRef.current?.clientWidth ?? 0) - 270), top: hover.y + 14 }}
          >
            <div className="font-semibold text-ink">{hover.attrs.n}</div>
            <div className="text-muted">
              {hover.attrs.d} · {hover.attrs.s}
            </div>
            <div className="num mt-1 grid grid-cols-[auto_auto] gap-x-3 text-ink2">
              <span>Students</span>
              <span className="text-right">{fmt(Number(hover.attrs.st))}</span>
              <span>Rooms available</span>
              <span className="text-right">{fmt(Number(hover.attrs.a))}</span>
              <span>Rooms required</span>
              <span className="text-right">{fmt(Number(hover.attrs.r))}</span>
              <span className="font-semibold text-ink">Gap</span>
              <span className="text-right font-semibold text-ink">{fmtGap(Number(hover.attrs.gap))}</span>
            </div>
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-2.5 text-xs text-ink2">
        <span className="font-medium text-ink">Classroom gap</span>
        {GAP_CLASSES.map((c) => (
          <span key={c.label} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: c[dotMode] }} />
            {c.label}
          </span>
        ))}
        <span className="text-muted">· dot size = students</span>
        <span className="ml-auto text-muted">
          {fmt(mapped)} of {fmt(rows.length)} schools mapped{basemapName ? ` · ${basemapName}` : ''}
        </span>
      </div>
    </div>
  );
}
