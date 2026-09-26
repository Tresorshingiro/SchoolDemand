import { useEffect, useMemo, useRef, useState } from 'react';
import esriConfig from '@arcgis/core/config';
import { version as arcgisVersion } from '@arcgis/core/kernel';
import ArcGISMap from '@arcgis/core/Map';
import MapView from '@arcgis/core/views/MapView';
import Basemap from '@arcgis/core/Basemap';
import TileLayer from '@arcgis/core/layers/TileLayer';
import OpenStreetMapLayer from '@arcgis/core/layers/OpenStreetMapLayer';
import GeoJSONLayer from '@arcgis/core/layers/GeoJSONLayer';
import GraphicsLayer from '@arcgis/core/layers/GraphicsLayer';
import FeatureReductionCluster from '@arcgis/core/layers/support/FeatureReductionCluster';
import AggregateField from '@arcgis/core/layers/support/AggregateField';
import LabelClass from '@arcgis/core/layers/support/LabelClass';
import ClassBreaksRenderer from '@arcgis/core/renderers/ClassBreaksRenderer';
import SimpleRenderer from '@arcgis/core/renderers/SimpleRenderer';
import SimpleMarkerSymbol from '@arcgis/core/symbols/SimpleMarkerSymbol';
import SimpleFillSymbol from '@arcgis/core/symbols/SimpleFillSymbol';
import TextSymbol from '@arcgis/core/symbols/TextSymbol';
import Graphic from '@arcgis/core/Graphic';
import Polygon from '@arcgis/core/geometry/Polygon';
import Extent from '@arcgis/core/geometry/Extent';
import * as reactiveUtils from '@arcgis/core/core/reactiveUtils';
import '@arcgis/core/assets/esri/themes/light/main.css';

import { fmt, fmtGap, type SchoolLevel } from '../data';
import { COLORS, GAP_CLASSES, STATUS_COLORS, type Mode } from '../theme';
import { onBeforePrint, usePrinting } from '../print';
import { API_URL } from '../api';

// Same setup as BTS ecofleet-web: with Vite, @arcgis/core must fetch its assets from the CDN.
esriConfig.assetsPath = `https://js.arcgis.com/${arcgisVersion}/@arcgis/core/assets`;
const ARCGIS_TOKEN = import.meta.env.VITE_ARCGIS_TOKEN as string | undefined;
if (ARCGIS_TOKEN) esriConfig.apiKey = ARCGIS_TOKEN;

const BOUNDARIES = `${API_URL}/boundaries`; // GeoJSON from the database (PostGIS)
const RWANDA_CENTER: [number, number] = [29.87, -1.94];
// Rwanda plus a margin: the view cannot be panned away from it
const RWANDA_EXTENT = new Extent({ xmin: 28.7, ymin: -3.0, xmax: 31.05, ymax: -0.9, spatialReference: { wkid: 4326 } });
const SERVICES = 'https://services.arcgisonline.com/ArcGIS/rest/services';
const CANVAS = {
  light: `${SERVICES}/Canvas/World_Light_Gray_Base/MapServer`,
  dark: `${SERVICES}/Canvas/World_Dark_Gray_Base/MapServer`,
};
const IMAGERY = `${SERVICES}/World_Imagery/MapServer`;
const IMAGERY_LABELS = `${SERVICES}/Reference/World_Boundaries_and_Places/MapServer`;
const CLUSTER_MAX_SCALE = 150000; // zoomed in past ~1:150,000 every school is drawn on its own
// Zoomed in past ~1:40,000 (zoom 14+) a second layer takes over: every school the same large size, with its name
// (GIS team's advice: at street level, sizes by students hide small schools next to big ones)
const NEAR_SCALE = 40000;
const NEAR_SIZE = 16;
const NAME_SCALE = 20000; // school names from about zoom 15
const FOCUS = [250, 178, 25, 1]; // outline of the district / sector picked in the filters (status "warning" amber)

export type BasemapKind = 'canvas' | 'satellite';
const BASEMAP_KEY = 'classroom-dashboard-basemap-v3'; // v3: everyone starts on imagery again (the blank-imagery bug is fixed)

function storedBasemap(): BasemapKind {
  try {
    return localStorage.getItem(BASEMAP_KEY) === 'canvas' ? 'canvas' : 'satellite';
  } catch {
    return 'satellite';
  }
}

/**
 * Esri World Imagery with place labels, or the grey canvas (both keyless, as in BTS), built at once. The basemap is
 * given to the map when the map is created: a basemap attached later, while the view is still animating to Rwanda,
 * can stay suspended and never draw (ArcGIS 4.34) — the blank imagery seen before.
 */
function makeBasemap(mode: Mode, kind: BasemapKind): Basemap {
  if (kind === 'satellite') {
    return new Basemap({
      title: 'Satellite imagery',
      // The imagery over Rwanda is dark at national scale: lift it a little so the landscape reads
      baseLayers: [new TileLayer({ url: IMAGERY, effect: 'brightness(1.12) contrast(1.05) saturate(1.3)' })],
      // Esri's place names only close up (about zoom 13+): further out they show neighbouring towns, old names
      // (Gitarama, Butare) and cell names that crowd our district / sector labels
      referenceLayers: [new TileLayer({ url: IMAGERY_LABELS, minScale: 80000 })],
    });
  }
  return new Basemap({ baseLayers: [new TileLayer({ url: CANVAS[mode] })], title: mode === 'dark' ? 'Dark grey canvas' : 'Light grey canvas' });
}

const basemapKey = (mode: Mode, kind: BasemapKind) => (kind === 'satellite' ? kind : `${kind}|${mode}`);

/**
 * Put `first` on the map and make sure it draws: when its tiles cannot load, fall back imagery -> canvas ->
 * OpenStreetMap; when its layer view stays suspended, give the map a fresh copy once.
 */
async function showBasemap(view: MapView, first: Basemap, mode: Mode, onTitle: (t: string) => void): Promise<void> {
  const chain = [first, ...(first.title === 'Satellite imagery' ? [makeBasemap(mode, 'canvas')] : []),
    new Basemap({ baseLayers: [new OpenStreetMapLayer()], title: 'OpenStreetMap' })];
  const gone = () => view.destroyed || !view.map; // the view can be destroyed while a basemap loads
  for (const basemap of chain) {
    if (gone()) return;
    if (view.map!.basemap !== basemap) view.map!.basemap = basemap;
    onTitle(basemap.title);
    const layer = basemap.baseLayers.getItemAt(0);
    if (!layer) continue;
    try {
      await layer.load();
    } catch {
      continue; // service unreachable: next basemap
    }
    const lv = await view.whenLayerView(layer).catch(() => null);
    if (gone()) return;
    await reactiveUtils.whenOnce(() => view.stationary);
    if (gone()) return;
    if (lv?.suspended && view.map!.basemap === basemap) view.map!.basemap = makeBasemap(mode, basemap.title === 'Satellite imagery' ? 'satellite' : 'canvas');
    return;
  }
}

/** Gap classes as continuous ranges, so a cluster's average gap (e.g. -3.4) also finds its class. */
const BREAKS = GAP_CLASSES.map((c, i) => ({
  ...c,
  lo: i === 0 ? -1e6 : c.min - 0.5,
  hi: i === GAP_CLASSES.length - 1 ? 1e6 : c.max + 0.5,
}));
const breakOf = (gap: number) => BREAKS.find((b) => gap >= b.lo && gap < b.hi)!;

/** Deficit / Exact fit / Surplus, each a group of gap classes (the map's status filter). */
const STATUSES = [
  { key: 'Deficit' as const, classes: GAP_CLASSES.filter((c) => c.max < 0).map((c) => c.label) },
  { key: 'Exact fit' as const, classes: GAP_CLASSES.filter((c) => c.min === 0 && c.max === 0).map((c) => c.label) },
  { key: 'Surplus' as const, classes: GAP_CLASSES.filter((c) => c.min > 0).map((c) => c.label) },
];

type Outline = { color: string | number[]; width: number };

function makeRenderer(field: string, mode: Mode, outline: Outline, size: __esri.SizeVariableProperties) {
  return new ClassBreaksRenderer({
    field,
    classBreakInfos: BREAKS.map((c) => ({
      minValue: c.lo,
      maxValue: c.hi,
      label: c.label,
      symbol: new SimpleMarkerSymbol({ style: 'circle', size: 7, color: c[mode], outline }),
    })),
    visualVariables: [size],
  });
}

/** Nearby schools grouped: colour = average gap, size and label = number of schools. */
function makeClusters(mode: Mode) {
  return new FeatureReductionCluster({
    clusterRadius: '60px',
    clusterMinSize: '16px',
    clusterMaxSize: '46px',
    maxScale: CLUSTER_MAX_SCALE,
    fields: [
      new AggregateField({ name: 'avg_gap', onStatisticField: 'gap', statisticType: 'avg' }),
      new AggregateField({ name: 'sum_short', onStatisticField: 'sh', statisticType: 'sum' }),
      new AggregateField({ name: 'sum_st', onStatisticField: 'st', statisticType: 'sum' }),
      new AggregateField({ name: 'n_deficit', onStatisticField: 'def', statisticType: 'sum' }),
    ],
    renderer: makeRenderer('avg_gap', mode, { color: '#ffffff', width: 1.25 }, {
      type: 'size', field: 'cluster_count',
      stops: [{ value: 1, size: 12 }, { value: 25, size: 24 }, { value: 150, size: 36 }, { value: 500, size: 46 }],
    } as __esri.SizeVariableProperties),
    labelingInfo: [new LabelClass({
      deconflictionStrategy: 'none',
      labelPlacement: 'center-center',
      labelExpressionInfo: { expression: "Text($feature.cluster_count, '#,###')" },
      symbol: new TextSymbol({
        color: '#ffffff', haloColor: 'rgba(0,0,0,0.55)', haloSize: 1,
        font: { family: 'Noto Sans', size: 9, weight: 'bold' },
      }),
    })],
    popupEnabled: false,
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
        properties: {
          c: r.c, n: r.n, d: r.d, s: r.s, st: r.st, g: r.g, ds: r.ds, a: r.a, r: r.r, gap: r.gap,
          sh: Math.max(-r.gap, 0), def: r.gap < 0 ? 1 : 0,
        },
      })),
  };
}

/** Everything outside Rwanda, as a world polygon with Rwanda cut out. */
function maskPolygon(outline: GeoJSON.Geometry): Polygon {
  const polys = outline.type === 'Polygon' ? [outline.coordinates] : outline.type === 'MultiPolygon' ? outline.coordinates : [];
  const area = (ring: number[][]) => ring.reduce((s, [x1, y1], i) => {
    const [x2, y2] = ring[(i + 1) % ring.length];
    return s + (x1 * y2 - x2 * y1);
  }, 0);
  // ArcGIS: outer rings clockwise, holes counter-clockwise (positive signed area here)
  const holes = polys.map((p) => (area(p[0]) > 0 ? p[0] : [...p[0]].reverse()));
  const world = [[-179, -85], [-179, 85], [179, 85], [179, -85], [-179, -85]];
  return new Polygon({ rings: [world, ...holes], spatialReference: { wkid: 4326 } });
}

/** Line colour, mask fill and label colours for the basemap in use. */
function boundaryStyle(mode: Mode, kind: BasemapKind) {
  const light = kind === 'satellite' || mode === 'dark';
  return {
    line: kind === 'satellite' ? [255, 255, 255] : mode === 'dark' ? [200, 200, 195] : [60, 60, 58],
    mask: kind === 'satellite' ? [0, 0, 0, 0.7] : mode === 'dark' ? [13, 13, 13, 0.85] : [249, 249, 247, 0.88],
    text: light ? '#ffffff' : '#252523',
    halo: light ? 'rgba(0,0,0,0.6)' : 'rgba(255,255,255,0.85)',
  };
}

function outlineRenderer(color: number[], width: number) {
  return new SimpleRenderer({ symbol: new SimpleFillSymbol({ color: [0, 0, 0, 0], outline: { color, width } }) });
}

// District names from about zoom 9 to 11 (at national scale they only fit between clusters here and there);
// sector names take over closer in.
const DISTRICT_LABEL_SCALES = { minScale: 1200000, maxScale: 300000 };
const SECTOR_LABEL_SCALES = { minScale: 300000 };

function areaLabels(field: string, size: number, bold: boolean, scales: { minScale?: number; maxScale?: number },
  style: ReturnType<typeof boundaryStyle>) {
  return [new LabelClass({
    labelExpressionInfo: { expression: bold ? `Upper($feature.${field})` : `$feature.${field}` },
    deconflictionStrategy: 'static',
    ...scales,
    symbol: new TextSymbol({
      color: style.text, haloColor: style.halo, haloSize: 1.25,
      font: { family: 'Noto Sans', size, weight: bold ? 'bold' : 'normal' },
    }),
  })];
}

interface Hover {
  x: number;
  y: number;
  attrs: Record<string, number | string>;
  cluster: boolean;
}

interface Props {
  rows: SchoolLevel[];
  mode: Mode;
  selected: number | null;
  onSelect: (code: number) => void;
  /** District / sector picked in the page filters: outlined on the map. */
  district?: string;
  sector?: string;
}

/** Check-box row of the legend panel: swatch (filled when shown), label, count. */
function LegendRow({ on, partly = false, color, label, count, indent = false, onClick }: {
  on: boolean; partly?: boolean; color: string; label: string; count?: number; indent?: boolean; onClick: () => void;
}) {
  return (
    <button type="button" role="checkbox" aria-checked={on ? true : partly ? 'mixed' : false} onClick={onClick}
      title={on ? `Hide ${label}` : `Show ${label}`}
      className={`flex w-full items-center gap-2 rounded px-1.5 py-[3px] text-left hover:bg-[var(--line)] ${
        indent ? 'pl-5 text-[11px]' : 'text-xs font-medium'} ${on || partly ? 'text-ink' : 'text-muted'}`}>
      <span className="inline-block shrink-0 rounded-full"
        style={{
          width: indent ? 9 : 11, height: indent ? 9 : 11,
          background: on ? color : partly ? `linear-gradient(90deg, ${color} 50%, transparent 50%)` : 'transparent',
          boxShadow: `inset 0 0 0 1.5px ${color}`,
        }} />
      <span className={`flex-1 truncate ${on || partly ? '' : 'line-through'}`}>{label}</span>
      {count !== undefined && <span className="num text-[11px] text-muted">{fmt(count)}</span>}
    </button>
  );
}

function LegendCheck({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" role="checkbox" aria-checked={on} onClick={onClick}
      className={`flex items-center gap-1.5 rounded px-1.5 py-[3px] text-xs hover:bg-[var(--line)] ${on ? 'text-ink' : 'text-muted'}`}>
      <span className={`grid h-3 w-3 place-items-center rounded-[3px] border ${on ? 'border-accent bg-accent text-white' : 'border-[var(--muted)]'}`}>
        {on && (
          <svg viewBox="0 0 12 12" width="9" height="9" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M2.5 6.2 5 8.5l4.5-5" />
          </svg>
        )}
      </span>
      {label}
    </button>
  );
}

export default function SchoolMap({ rows, mode, selected, onSelect, district = '', sector = '' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<MapView | null>(null);
  const layersRef = useRef<GeoJSONLayer[]>([]); // the school layers: overview (clusters / sized dots) and near
  const bounds = useRef<{ districts: GeoJSONLayer; sectors: GeoJSONLayer; mask: GraphicsLayer; focus: GraphicsLayer } | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const [basemapName, setBasemapName] = useState('');
  const [kind, setKind] = useState<BasemapKind>(storedBasemap);
  const [clustered, setClustered] = useState(true);
  const [showDistricts, setShowDistricts] = useState(true);
  const [showSectors, setShowSectors] = useState(true);
  const [hidden, setHidden] = useState<Set<string>>(new Set()); // gap classes switched off in the legend
  const [query, setQuery] = useState('');
  const [notFound, setNotFound] = useState(false);
  // Printing: the WebGL canvas does not print, so a screenshot of the view stands in for it.
  const printing = usePrinting();
  const [shot, setShot] = useState<string | null>(null);
  const pendingRef = useRef<Promise<unknown>>(Promise.resolve()); // basemap / school layer still loading
  const shownBasemap = useRef(''); // basemapKey of the basemap on the map
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
  const shown = useMemo(() => rows.filter((r) => r.x !== null && !hidden.has(breakOf(r.gap).label)).length, [rows, hidden]);
  const classCount = useMemo(() => {
    const n = new Map<string, number>();
    for (const r of rows) if (r.x !== null) n.set(breakOf(r.gap).label, (n.get(breakOf(r.gap).label) ?? 0) + 1);
    return n;
  }, [rows]);
  const [legendOpen, setLegendOpen] = useState(true);
  const statusCount = useMemo(() => {
    const n = { Deficit: 0, 'Exact fit': 0, Surplus: 0 };
    for (const r of rows) if (r.x !== null) n[r.gap < 0 ? 'Deficit' : r.gap === 0 ? 'Exact fit' : 'Surplus'] += 1;
    return n;
  }, [rows]);
  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    return rows.filter((r) => r.n.toLowerCase().includes(q) || String(r.c).startsWith(q)).slice(0, 8);
  }, [rows, query]);

  const pick = (code: number) => {
    onSelect(code);
    setQuery('');
    setNotFound(false);
  };
  const findSchool = () => {
    const q = query.trim().toLowerCase();
    const hit = rows.find((r) => String(r.c) === q) ?? rows.find((r) => r.n.toLowerCase() === q) ?? suggestions[0];
    if (hit) pick(hit.c);
    else setNotFound(true);
  };

  // Create the view, the mask and the boundary layers once.
  useEffect(() => {
    if (!containerRef.current) return;
    const style = boundaryStyle(mode, kind);
    const mask = new GraphicsLayer({ title: 'Outside Rwanda', listMode: 'hide' });
    const districts = new GeoJSONLayer({
      url: `${BOUNDARIES}/districts`, title: 'Districts', outFields: ['d'],
      renderer: outlineRenderer([...style.line, 0.9], 1.5),
      labelingInfo: areaLabels('d', 9, true, DISTRICT_LABEL_SCALES, style),
    });
    const sectors = new GeoJSONLayer({
      url: `${BOUNDARIES}/sectors`, title: 'Sectors', outFields: ['d', 's'],
      minScale: 1200000, // from about zoom 9
      renderer: outlineRenderer([...style.line, 0.45], 0.6),
      labelingInfo: areaLabels('s', 9, false, SECTOR_LABEL_SCALES, style),
    });
    const focus = new GraphicsLayer({ title: 'Selected area', listMode: 'hide' });
    // The mask sits above the boundaries: district shapes reach into Lake Kivu, beyond the country outline
    const basemap = makeBasemap(mode, kind);
    shownBasemap.current = basemapKey(mode, kind);
    const map = new ArcGISMap({ basemap, layers: [sectors, districts, mask, focus] });
    const view = new MapView({
      container: containerRef.current,
      map,
      center: RWANDA_CENTER,
      zoom: 8,
      constraints: { minZoom: 8, maxZoom: 18, rotationEnabled: false, geometry: RWANDA_EXTENT },
      ui: { components: ['zoom', 'attribution'] },
      popupEnabled: false,
    });
    viewRef.current = view;
    bounds.current = { districts, sectors, mask, focus };
    pendingRef.current = showBasemap(view, basemap, mode, setBasemapName);

    fetch(`${BOUNDARIES}/country`)
      .then((res) => res.json() as Promise<GeoJSON.FeatureCollection>)
      .then((fc) => mask.add(new Graphic({
        geometry: maskPolygon(fc.features[0].geometry),
        symbol: new SimpleFillSymbol({ color: style.mask, outline: { color: [...style.line, 1], width: 2 } }),
      })))
      .catch(() => undefined); // the map still works without the mask

    const hitLayer = async (event: __esri.ViewClickEvent | __esri.ViewPointerMoveEvent) => {
      if (!layersRef.current.length) return null;
      const res = await view.hitTest(event, { include: layersRef.current });
      const hit = res.results.find((r): r is __esri.GraphicHit => r.type === 'graphic');
      return hit?.graphic ?? null;
    };

    const click = view.on('click', async (event) => {
      const g = await hitLayer(event);
      if (!g) return;
      if (g.isAggregate) view.goTo({ target: g.geometry, zoom: view.zoom + 2 }, { duration: 500 }).catch(() => undefined);
      else onSelectRef.current(Number(g.attributes.c));
    });

    let frame = 0;
    const move = view.on('pointer-move', (event) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(async () => {
        const g: Graphic | null = await hitLayer(event);
        if (containerRef.current) containerRef.current.style.cursor = g ? 'pointer' : '';
        setHover(g ? { x: event.x, y: event.y, attrs: g.attributes, cluster: !!g.isAggregate } : null);
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
      layersRef.current = [];
      bounds.current = null;
    };
    // Created once; the effect below restyles the layers for the theme and basemap.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Basemap follows the Satellite / Map switch (and the theme on the Map); boundaries and mask restyle with it.
  useEffect(() => {
    const view = viewRef.current;
    if (view?.map && shownBasemap.current !== basemapKey(mode, kind)) {
      shownBasemap.current = basemapKey(mode, kind);
      pendingRef.current = showBasemap(view, makeBasemap(mode, kind), mode, setBasemapName);
    }
    const b = bounds.current;
    if (b) {
      const style = boundaryStyle(mode, kind);
      b.mask.graphics.forEach((g) => {
        g.symbol = new SimpleFillSymbol({ color: style.mask, outline: { color: [...style.line, 1], width: 2 } });
      });
      b.districts.renderer = outlineRenderer([...style.line, 0.9], 1.5);
      b.sectors.renderer = outlineRenderer([...style.line, 0.45], 0.6);
      b.districts.labelingInfo = areaLabels('d', 9, true, DISTRICT_LABEL_SCALES, style);
      b.sectors.labelingInfo = areaLabels('s', 9, false, SECTOR_LABEL_SCALES, style);
    }
  }, [mode, kind]);

  // Boundary switches
  useEffect(() => {
    const b = bounds.current;
    if (!b) return;
    b.districts.visible = showDistricts;
    b.sectors.visible = showSectors;
  }, [showDistricts, showSectors]);

  // Outline the district / sector picked in the page filters
  useEffect(() => {
    const b = bounds.current;
    if (!b || !ready) return;
    b.focus.removeAll();
    if (!district) return;
    const layer = sector ? b.sectors : b.districts;
    const esc = (v: string) => v.replace(/'/g, "''");
    const where = sector ? `d = '${esc(district)}' AND s = '${esc(sector)}'` : `d = '${esc(district)}'`;
    let cancelled = false;
    layer.queryFeatures({ where, returnGeometry: true, outFields: [] }).then(({ features }) => {
      if (cancelled) return;
      for (const f of features) {
        b.focus.add(new Graphic({
          geometry: f.geometry,
          symbol: new SimpleFillSymbol({ color: [0, 0, 0, 0], outline: { color: FOCUS, width: 3 } }),
        }));
      }
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [district, sector, ready]);

  // Rebuild the school layer whenever the filtered rows, theme or display change.
  useEffect(() => {
    const map = viewRef.current?.map;
    if (!map || !ready) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(toGeoJSON(rows))], { type: 'application/json' }));
    // On imagery a white ring keeps every class readable against fields, forest and roofs.
    const outline = kind === 'satellite' ? { color: '#ffffff', width: 1 } : { color: COLORS[mode].surface, width: 0.75 };
    const visible = BREAKS.filter((b) => !hidden.has(b.label));
    const common = {
      url,
      outFields: ['*'],
      definitionExpression: visible.length === BREAKS.length ? undefined
        : visible.length ? visible.map((b) => `(gap >= ${b.lo} AND gap < ${b.hi})`).join(' OR ') : '1 = 0',
      orderBy: [{ field: 'gap', order: 'ascending' as const }], // largest deficits drawn on top
      popupEnabled: false,
    };
    // Overview: clusters, then dots sized by students, down to NEAR_SCALE
    const overview = new GeoJSONLayer({
      ...common,
      title: 'Schools',
      maxScale: NEAR_SCALE,
      renderer: makeRenderer('gap', dotMode, outline, {
        type: 'size', field: 'st',
        stops: [{ value: 50, size: 4 }, { value: 1000, size: 7 }, { value: 4000, size: 13 }],
      } as __esri.SizeVariableProperties),
      featureReduction: clustered ? makeClusters(dotMode) : null,
    });
    // Near: same colours, every school the same large size, names when close
    const near = new GeoJSONLayer({
      ...common,
      title: 'Schools (close up)',
      minScale: NEAR_SCALE,
      renderer: new ClassBreaksRenderer({
        field: 'gap',
        classBreakInfos: BREAKS.map((c) => ({
          minValue: c.lo, maxValue: c.hi, label: c.label,
          symbol: new SimpleMarkerSymbol({ style: 'circle', size: NEAR_SIZE, color: c[dotMode], outline: { ...outline, width: 1.75 } }),
        })),
      }),
      labelingInfo: [new LabelClass({
        labelExpressionInfo: { expression: '$feature.n' },
        labelPlacement: 'above-center',
        minScale: NAME_SCALE,
        symbol: new TextSymbol({
          color: kind === 'satellite' || mode === 'dark' ? '#ffffff' : '#0b0b0b',
          haloColor: kind === 'satellite' || mode === 'dark' ? 'rgba(0,0,0,0.7)' : 'rgba(255,255,255,0.9)',
          haloSize: 1.25, font: { family: 'Noto Sans', size: 10, weight: 'bold' },
        }),
      })],
    });
    const layers = [overview, near];
    const focus = bounds.current?.focus;
    for (const layer of layers) {
      layer.load().catch(() => undefined); // replaced while loading (filter / display change): nothing to report
      map.add(layer, focus ? map.layers.indexOf(focus) : undefined); // under the selected-area outline
    }
    layersRef.current = layers;
    pendingRef.current = Promise.all([pendingRef.current, ...layers.map((l) => l.when().catch(() => undefined))]);
    // The layers read the blob while loading; release it once both are done.
    let released = false;
    const settled = Promise.allSettled(layers.map((l) => l.when()));
    settled.then(() => {
      if (!released) URL.revokeObjectURL(url);
      released = true;
    });
    return () => {
      for (const layer of layers) {
        map.remove(layer);
        if (layer.loaded) layer.destroy();
      }
      // A layer still loading is released with the blob once it settles.
    };
  }, [rows, dotMode, kind, mode, ready, clustered, hidden]);

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

  // Zoom to the filtered schools (not on theme or display changes).
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

  // Highlight and fly to the selected school, close enough to see it on its own with its name.
  useEffect(() => {
    const view = viewRef.current;
    const layers = layersRef.current;
    if (!view || !layers.length || selected === null) return;
    const handles: __esri.Handle[] = [];
    let cancelled = false;
    (async () => {
      const { features } = await layers[0].queryFeatures({ where: `c = ${selected}`, returnGeometry: true, outFields: ['c'] });
      if (cancelled || !features.length) return;
      await view.goTo({ target: features[0].geometry, zoom: Math.max(view.zoom, 15) }, { duration: 600 }).catch(() => undefined);
      for (const layer of layers) {
        const lv = await view.whenLayerView(layer);
        const q = await layer.queryFeatures({ where: `c = ${selected}`, returnGeometry: false, outFields: ['c'] });
        if (!cancelled && q.features.length) handles.push(lv.highlight(q.features[0]));
      }
    })().catch(() => undefined);
    return () => {
      cancelled = true;
      handles.forEach((h) => h.remove());
    };
  }, [selected, rows, dotMode, kind, clustered, hidden]);

  // A status is on when all its classes show; clicking it hides them all, or shows them all again
  const toggleStatus = (classes: string[]) =>
    setHidden((h) => {
      const next = new Set(h);
      const allOn = classes.every((c) => !h.has(c));
      classes.forEach((c) => (allOn ? next.add(c) : next.delete(c)));
      return next;
    });

  const toggleClass = (label: string) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });

  const panel = 'rounded-lg border border-line bg-surface shadow-lg';
  return (
    <div className="relative h-full min-h-[480px] overflow-hidden">
      <div ref={containerRef} className="absolute inset-0" aria-label="Map of schools coloured by classroom gap" />
      {printing && shot && (
        <img src={shot} alt="Map of schools coloured by classroom gap" className="absolute inset-0 z-20 h-full w-full object-cover" />
      )}

      {/* Top left, beside the zoom buttons: find a school */}
      {ready && (
        <div className="absolute left-[60px] top-[15px] z-10 w-64 print:hidden">
          <div className={`${panel} flex items-center gap-2 px-2.5`}>
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
              className="shrink-0 text-muted" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input type="search" value={query} placeholder="Find a school…" aria-label="Find a school on the map"
              onChange={(e) => {
                setQuery(e.target.value);
                setNotFound(false);
              }}
              onKeyDown={(e) => e.key === 'Enter' && findSchool()}
              className="h-8 w-full border-0 bg-transparent px-0 text-xs focus-visible:outline-none" />
          </div>
          {notFound && <div className={`${panel} mt-1 px-3 py-1.5 text-xs text-[var(--deficit)]`}>No school found in this view</div>}
          {suggestions.length > 0 && (
            <ul className={`${panel} mt-1 overflow-hidden text-xs`}>
              {suggestions.map((r) => (
                <li key={r.c}>
                  <button type="button" className="flex w-full justify-between gap-2 px-3 py-1.5 text-left hover:bg-[var(--line)]"
                    onClick={() => pick(r.c)}>
                    <span className="truncate text-ink">{r.n}</span>
                    <span className="shrink-0 text-muted">{r.s} · {fmtGap(r.gap)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Top right: basemap */}
      {ready && (
        <div className={`${panel} absolute right-3 top-3 z-10 flex gap-0.5 p-0.5 print:hidden`} role="radiogroup" aria-label="Basemap">
          {(['satellite', 'canvas'] as const).map((k) => (
            <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => chooseKind(k)}
              className={`rounded-md px-3 py-1 text-xs font-medium ${kind === k ? 'bg-accent text-white' : 'text-ink2 hover:text-ink'}`}>
              {k === 'canvas' ? 'Map' : 'Satellite'}
            </button>
          ))}
        </div>
      )}

      {/* Bottom left: the legend, which is also the map's filter */}
      <div className={`${panel} absolute bottom-7 left-3 z-10 w-[236px] text-ink2`}>
        <button type="button" onClick={() => setLegendOpen((o) => !o)} aria-expanded={legendOpen}
          className="flex w-full items-center justify-between gap-3 whitespace-nowrap px-3 py-2 text-left text-xs font-semibold text-ink">
          <span>Classroom gap</span>
          <span className="flex items-center gap-2 font-normal text-muted" title={`${fmt(shown)} of ${fmt(mapped)} schools shown`}>
            <span className="num">{fmt(shown)} / {fmt(mapped)}</span>
            <svg viewBox="0 0 12 12" width="10" height="10" className={`transition-transform print:hidden ${legendOpen ? '' : 'rotate-180'}`}
              fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="m2.5 7.5 3.5-3.5 3.5 3.5" />
            </svg>
          </span>
        </button>
        {legendOpen && (
          <div className="border-t border-line px-1.5 pb-2 pt-1.5">
            {STATUSES.map(({ key, classes }) => {
              const on = classes.every((c) => !hidden.has(c));
              const partly = !on && classes.some((c) => !hidden.has(c));
              return (
                <div key={key}>
                  <LegendRow on={on} partly={partly} color={STATUS_COLORS[dotMode][key]} label={key} count={statusCount[key]}
                    onClick={() => toggleStatus(classes)} />
                  {classes.length > 1 && classes.map((label) => {
                    const c = GAP_CLASSES.find((g) => g.label === label)!;
                    return (
                      <LegendRow key={label} indent on={!hidden.has(label)} color={c[dotMode]} label={label}
                        count={classCount.get(label) ?? 0} onClick={() => toggleClass(label)} />
                    );
                  })}
                </div>
              );
            })}
            <div className="mt-1.5 flex items-center justify-between border-t border-line px-1.5 pt-2 print:hidden">
              <div className="flex gap-0.5 rounded-md bg-[var(--line)] p-0.5" role="radiogroup" aria-label="Show schools as">
                {([[true, 'Clusters'], [false, 'Schools']] as const).map(([v, label]) => (
                  <button key={label} type="button" role="radio" aria-checked={clustered === v} onClick={() => setClustered(v)}
                    className={`rounded px-2 py-0.5 text-[11px] ${clustered === v ? 'bg-surface font-medium text-ink shadow-sm' : 'text-ink2 hover:text-ink'}`}>
                    {label}
                  </button>
                ))}
              </div>
              {hidden.size > 0 && (
                <button type="button" className="text-[11px] text-accent hover:underline" onClick={() => setHidden(new Set())}>
                  Show all
                </button>
              )}
            </div>
            <p className="px-1.5 pt-1.5 text-[11px] leading-snug text-muted">
              {clustered ? 'Circle = nearby schools grouped; colour = their average gap, number = schools. ' : 'Dot size = students. '}
              Zoom in to see each school with its name.
            </p>
            <div className="mt-1.5 flex gap-1 border-t border-line pt-1.5 print:hidden">
              <LegendCheck on={showDistricts} label="Districts" onClick={() => setShowDistricts((v) => !v)} />
              <LegendCheck on={showSectors} label="Sectors" onClick={() => setShowSectors((v) => !v)} />
            </div>
          </div>
        )}
      </div>

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
          className="pointer-events-none absolute z-30 max-w-[260px] rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-lg print:hidden"
          style={{ left: Math.min(hover.x + 14, (containerRef.current?.clientWidth ?? 0) - 270), top: hover.y + 14 }}
        >
          {hover.cluster ? (
            <>
              <div className="font-semibold text-ink">{fmt(Number(hover.attrs.cluster_count))} schools</div>
              <div className="num mt-1 grid grid-cols-[auto_auto] gap-x-3 text-ink2">
                <span>Students</span>
                <span className="text-right">{fmt(Math.round(Number(hover.attrs.sum_st)))}</span>
                <span>Schools in deficit</span>
                <span className="text-right">{fmt(Math.round(Number(hover.attrs.n_deficit)))}</span>
                <span className="font-semibold text-ink">Classrooms short</span>
                <span className="text-right font-semibold text-ink">{fmt(Math.round(Number(hover.attrs.sum_short)))}</span>
                <span>Average gap</span>
                <span className="text-right">{fmtGap(Math.round(Number(hover.attrs.avg_gap) * 10) / 10)}</span>
              </div>
              <div className="mt-1 text-muted">Click to zoom in</div>
            </>
          ) : (
            <>
              <div className="font-semibold text-ink">{hover.attrs.n}</div>
              <div className="text-muted">{hover.attrs.d} · {hover.attrs.s}</div>
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
            </>
          )}
        </div>
      )}
      {basemapName && <span className="sr-only">Basemap: {basemapName}</span>}
    </div>
  );
}
