"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ExplainBlock } from "@/components/ui/ExplainBlock";
import { GlassPanel } from "@/components/ui/GlassPanel";
import {
  api,
  MapViewConfig,
  Product,
} from "@/lib/api-client";
import {
  productLabel,
  productShortLabel,
  sortProductsByKind,
} from "@/lib/product-labels";

type LayerState = {
  productId: number;
  visible: boolean;
  opacity: number;
};

type Props = {
  products: Product[];
};

const MercatorMapCanvas = dynamic(
  () =>
    import("@/components/MercatorMapCanvas").then((m) => m.MercatorMapCanvas),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center bg-[var(--map-ocean-deep)] text-sm text-fg-muted">
        Loading Mercator map…
      </div>
    ),
  }
);

const FALLBACK_CONFIG: MapViewConfig = {
  crs: "EPSG:3857",
  projection: "Web Mercator",
  west: 55,
  south: 12,
  east: 88,
  north: 40,
  center_lat: 30,
  center_lon: 69.5,
  default_zoom: 5,
  leaflet_bounds: [
    [12, 55],
    [40, 88],
  ],
};

export function DynamicImageViewer({ products }: Props) {
  const available = useMemo(
    () =>
      sortProductsByKind(
        products.filter((p) => p.availability_status === "generated")
      ),
    [products]
  );

  const byId = useMemo(() => {
    const m = new Map<number, Product>();
    products.forEach((p) => m.set(p.id, p));
    return m;
  }, [products]);

  const [mapConfig, setMapConfig] = useState<MapViewConfig>(FALLBACK_CONFIG);
  const [layers, setLayers] = useState<LayerState[]>([]);
  const [mapUrls, setMapUrls] = useState<Record<number, string>>({});
  const [addOpen, setAddOpen] = useState(true);
  const [pendingIds, setPendingIds] = useState<number[]>([]);
  const [ensureError, setEnsureError] = useState<string | null>(null);
  const [basemapOn, setBasemapOn] = useState(true);
  const [addingAll, setAddingAll] = useState(false);
  const mapUrlsRef = useRef(mapUrls);
  mapUrlsRef.current = mapUrls;
  /** Coalesce duplicate ensure kicks for the same product. */
  const kickedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    api
      .mapView()
      .then(setMapConfig)
      .catch(() => setMapConfig(FALLBACK_CONFIG));
  }, []);

  // Seed map URL cache from products that already have overlays
  useEffect(() => {
    const next: Record<number, string> = {};
    available.forEach((p) => {
      if (p.map_image_url) next[p.id] = p.map_image_url;
    });
    setMapUrls((prev) => ({ ...prev, ...next }));
  }, [available]);

  useEffect(() => {
    setLayers((prev) => {
      const nextIds = new Set(available.map((p) => p.id));
      const kept = prev.filter((l) => nextIds.has(l.productId));
      if (kept.length) return kept;
      const seed =
        available.find((p) => p.product_kind === "composite") || available[0];
      return seed
        ? [{ productId: seed.id, visible: true, opacity: 0.85 }]
        : [];
    });
  }, [available]);

  const markPending = useCallback((productId: number) => {
    setPendingIds((prev) =>
      prev.includes(productId) ? prev : [...prev, productId]
    );
  }, []);

  const clearPending = useCallback((productId: number) => {
    setPendingIds((prev) => prev.filter((id) => id !== productId));
    kickedRef.current.delete(productId);
  }, []);

  const ensureOverlay = useCallback(
    async (productId: number) => {
      if (mapUrlsRef.current[productId]) return mapUrlsRef.current[productId];
      if (kickedRef.current.has(productId)) return null;
      kickedRef.current.add(productId);
      markPending(productId);
      setEnsureError(null);
      try {
        const result = await api.ensureMapImage(productId);
        if (result.status === "ready" && result.map_image_url) {
          setMapUrls((prev) => ({
            ...prev,
            [productId]: result.map_image_url!,
          }));
          clearPending(productId);
          return result.map_image_url;
        }
        if (result.status === "generating" || result.status === "busy") {
          markPending(productId);
          return null;
        }
        clearPending(productId);
        setEnsureError(
          result.error || `Map overlay unavailable (${result.status})`
        );
        return null;
      } catch (e) {
        clearPending(productId);
        setEnsureError(e instanceof Error ? e.message : "Map overlay failed");
        return null;
      }
    },
    [clearPending, markPending]
  );

  // Kick non-blocking ensure for layers missing overlays.
  useEffect(() => {
    for (const layer of layers) {
      if (
        !mapUrlsRef.current[layer.productId] &&
        !kickedRef.current.has(layer.productId)
      ) {
        void ensureOverlay(layer.productId);
      }
    }
  }, [layers, ensureOverlay]);

  // Poll background generation until overlays are ready.
  useEffect(() => {
    if (!pendingIds.length) return;
    let cancelled = false;
    let running = false;

    const poll = async () => {
      if (running || document.visibilityState === "hidden") return;
      running = true;
      try {
        const results = await Promise.allSettled(
          pendingIds.map((id) => api.mapImageStatus(id))
        );
        if (cancelled) return;
        results.forEach((settled, index) => {
          const productId = pendingIds[index];
          if (settled.status !== "fulfilled") return;
          const result = settled.value;
          if (result.status === "ready" && result.map_image_url) {
            setMapUrls((prev) => ({
              ...prev,
              [productId]: result.map_image_url!,
            }));
            clearPending(productId);
          } else if (result.status === "busy") {
            kickedRef.current.delete(productId);
            void ensureOverlay(productId);
          } else if (
            result.status === "unavailable" &&
            !(result.error || "").toLowerCase().includes("raw file")
          ) {
            // Job lost after backend restart — re-queue.
            kickedRef.current.delete(productId);
            void ensureOverlay(productId);
          } else if (
            result.status === "error" ||
            result.status === "unavailable"
          ) {
            clearPending(productId);
            setEnsureError(
              result.error || `Map overlay failed for #${productId}`
            );
          }
        });
      } finally {
        running = false;
      }
    };

    const timer = window.setInterval(() => void poll(), 1500);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [pendingIds, clearPending, ensureOverlay]);

  const loadedIds = useMemo(
    () => new Set(layers.map((l) => l.productId)),
    [layers]
  );

  const addableChannels = available.filter(
    (p) => p.product_kind === "channel" && !loadedIds.has(p.id)
  );
  const addableComposites = available.filter(
    (p) => p.product_kind === "composite" && !loadedIds.has(p.id)
  );

  const ensuring = pendingIds[0] ?? null;

  async function addLayer(productId: number) {
    setLayers((prev) => {
      if (prev.some((l) => l.productId === productId)) return prev;
      return [...prev, { productId, visible: true, opacity: 0.85 }];
    });
    await ensureOverlay(productId);
  }

  async function addAllLayers() {
    if (addingAll) return;
    setAddingAll(true);
    setEnsureError(null);
    try {
      const toAdd = available.filter((p) => !loadedIds.has(p.id));
      setLayers((prev) => {
        const have = new Set(prev.map((l) => l.productId));
        const extra = toAdd
          .filter((p) => !have.has(p.id))
          .map((p) => ({ productId: p.id, visible: true, opacity: 0.85 }));
        return extra.length ? [...prev, ...extra] : prev;
      });
      // Queue each overlay job (non-blocking). Backend serializes satpy.
      for (const product of toAdd) {
        // eslint-disable-next-line no-await-in-loop
        await ensureOverlay(product.id);
      }
    } finally {
      setAddingAll(false);
    }
  }

  function removeAllLayers() {
    setLayers([]);
  }

  function removeLayer(productId: number) {
    setLayers((prev) => prev.filter((l) => l.productId !== productId));
  }

  function toggleVisible(productId: number) {
    setLayers((prev) =>
      prev.map((l) =>
        l.productId === productId ? { ...l, visible: !l.visible } : l
      )
    );
  }

  function setOpacity(productId: number, opacity: number) {
    setLayers((prev) =>
      prev.map((l) => (l.productId === productId ? { ...l, opacity } : l))
    );
  }

  function moveLayer(productId: number, direction: -1 | 1) {
    setLayers((prev) => {
      const idx = prev.findIndex((l) => l.productId === productId);
      if (idx < 0) return prev;
      const target = idx + direction;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      const [item] = next.splice(idx, 1);
      next.splice(target, 0, item);
      return next;
    });
  }

  function showOnly(productId: number) {
    setLayers((prev) =>
      prev.map((l) => ({ ...l, visible: l.productId === productId }))
    );
  }

  function showAll() {
    setLayers((prev) => prev.map((l) => ({ ...l, visible: true })));
  }

  function hideAll() {
    setLayers((prev) => prev.map((l) => ({ ...l, visible: false })));
  }

  const overlayLayers = useMemo(() => {
    return layers
      .map((layer, index) => {
        const url = mapUrls[layer.productId];
        if (!layer.visible || !url) return null;
        return {
          id: layer.productId,
          url,
          opacity: layer.opacity,
          zIndex: 200 + index,
        };
      })
      .filter(Boolean) as {
      id: number;
      url: string;
      opacity: number;
      zIndex: number;
    }[];
  }, [layers, mapUrls]);

  if (!products.length) return null;

  const bounds = mapConfig.leaflet_bounds;
  const center: [number, number] = [
    mapConfig.center_lat,
    mapConfig.center_lon,
  ];

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold text-accent-soft">Dynamic Image</h2>
      <ExplainBlock title="EUMETView-style Mercator layer stack">
        <p>
          Web Mercator map focused on{" "}
          <strong className="text-fg-heading">Pakistan</strong> within a large
          rectangular ROI ({mapConfig.west}°–{mapConfig.east}°E,{" "}
          {mapConfig.south}°–{mapConfig.north}°N) that also includes neighbouring
          countries. Each channel/composite (all 12 channels + 100 public
          composites when generated) is resampled to EPSG:3857 with a
          transparent background, then stacked with opacity — the same compositing
          principle as EUMETView (not a circular globe collage).
        </p>
      </ExplainBlock>

      <GlassPanel padding="sm" className="overflow-hidden">
        <div className="grid gap-4 lg:grid-cols-[minmax(260px,320px)_1fr]">
          <div className="flex max-h-[640px] flex-col gap-3 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs uppercase tracking-[0.16em] text-fg-subtle">
                Loaded layers · {layers.length}
              </p>
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  onClick={() => void addAllLayers()}
                  disabled={
                    addingAll ||
                    !available.length ||
                    layers.length >= available.length
                  }
                  className="rounded-full border border-glass-border px-2 py-0.5 text-[11px] text-fg-soft disabled:opacity-40 hover:bg-surface-hover"
                >
                  {addingAll ? "Queuing layers…" : "Add all layers"}
                </button>
                <button
                  type="button"
                  onClick={removeAllLayers}
                  disabled={!layers.length}
                  className="rounded-full border border-glass-border px-2 py-0.5 text-[11px] text-fg-soft disabled:opacity-40 hover:bg-surface-hover"
                >
                  Remove all layers
                </button>
                <button
                  type="button"
                  onClick={showAll}
                  disabled={!layers.length}
                  className="rounded-full border border-glass-border px-2 py-0.5 text-[11px] text-fg-soft disabled:opacity-40 hover:bg-surface-hover"
                >
                  Show all
                </button>
                <button
                  type="button"
                  onClick={hideAll}
                  disabled={!layers.length}
                  className="rounded-full border border-glass-border px-2 py-0.5 text-[11px] text-fg-soft disabled:opacity-40 hover:bg-surface-hover"
                >
                  Hide all
                </button>
              </div>
            </div>

            <label className="flex items-center gap-2 rounded-lg border border-glass-border bg-surface-panel px-2.5 py-1.5 text-xs text-fg-soft">
              <input
                type="checkbox"
                checked={basemapOn}
                onChange={(e) => setBasemapOn(e.target.checked)}
                className="accent-accent"
              />
              Basemap + coastlines (CARTO / OSM)
            </label>

            {pendingIds.length ? (
              <p className="rounded-lg border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-xs text-accent-soft">
                Building Mercator overlays in background
                {pendingIds.length === 1
                  ? ` (#${pendingIds[0]})`
                  : ` (${pendingIds.length} queued)`}
                . You can keep browsing while this runs.
              </p>
            ) : null}
            {ensureError ? (
              <p className="rounded-lg border border-rose-400/35 bg-rose-500/10 px-2.5 py-1.5 text-xs text-rose-700 theme-dark:text-rose-200">
                {ensureError}
              </p>
            ) : null}

            <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
              {layers.length === 0 ? (
                <li className="rounded-xl border border-dashed border-glass-border p-3 text-sm text-fg-muted">
                  No layers on the map. Use Add layers below.
                </li>
              ) : (
                [...layers].reverse().map((layer, revIdx) => {
                  const product = byId.get(layer.productId);
                  if (!product) return null;
                  const stackIndex = layers.length - 1 - revIdx;
                  const ready = Boolean(mapUrls[layer.productId]);
                  return (
                    <li
                      key={layer.productId}
                      className={[
                        "rounded-xl border border-glass-border bg-surface-panel p-3",
                        layer.visible ? "" : "opacity-60",
                      ].join(" ")}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate font-medium text-fg-heading">
                            {productLabel(product.product_name)}
                          </div>
                          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-fg-subtle">
                            <code className="rounded bg-surface-hover px-1.5 py-0.5 font-mono text-[10px] text-fg-soft">
                              {productShortLabel(product.product_name)}
                            </code>
                            <span className="capitalize">
                              {product.product_kind}
                            </span>
                            {!ready ? (
                              <span className="text-accent-amber">building…</span>
                            ) : null}
                          </div>
                        </div>
                        <div className="flex shrink-0 gap-1">
                          <button
                            type="button"
                            title="Move up in stack"
                            disabled={stackIndex >= layers.length - 1}
                            onClick={() => moveLayer(layer.productId, 1)}
                            className="rounded-md border border-glass-border px-1.5 py-0.5 text-xs text-fg-soft disabled:opacity-30 hover:bg-surface-hover"
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            title="Move down in stack"
                            disabled={stackIndex <= 0}
                            onClick={() => moveLayer(layer.productId, -1)}
                            className="rounded-md border border-glass-border px-1.5 py-0.5 text-xs text-fg-soft disabled:opacity-30 hover:bg-surface-hover"
                          >
                            ↓
                          </button>
                        </div>
                      </div>

                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => toggleVisible(layer.productId)}
                          className={[
                            "rounded-full border px-2.5 py-1 text-[11px] font-medium transition",
                            layer.visible
                              ? "border-accent/50 bg-accent/15 text-accent-soft"
                              : "border-glass-border text-fg-muted hover:bg-surface-hover",
                          ].join(" ")}
                          aria-pressed={layer.visible}
                        >
                          {layer.visible ? "Visible" : "Hidden"}
                        </button>
                        <button
                          type="button"
                          onClick={() => showOnly(layer.productId)}
                          className="rounded-full border border-glass-border px-2.5 py-1 text-[11px] text-fg-soft hover:bg-surface-hover"
                        >
                          Solo
                        </button>
                        <button
                          type="button"
                          onClick={() => removeLayer(layer.productId)}
                          className="rounded-full border border-rose-400/35 px-2.5 py-1 text-[11px] text-rose-700 theme-dark:text-rose-200 hover:bg-rose-500/10"
                        >
                          Remove
                        </button>
                      </div>

                      <label className="mt-2 flex items-center gap-2 text-[11px] text-fg-muted">
                        <span className="w-12 shrink-0">Opacity</span>
                        <input
                          type="range"
                          min={0.05}
                          max={1}
                          step={0.05}
                          value={layer.opacity}
                          onChange={(e) =>
                            setOpacity(layer.productId, Number(e.target.value))
                          }
                          className="h-1.5 w-full accent-accent"
                          disabled={!layer.visible}
                        />
                        <span className="w-8 text-right tabular-nums text-fg-soft">
                          {Math.round(layer.opacity * 100)}%
                        </span>
                      </label>
                    </li>
                  );
                })
              )}
            </ul>

            <div className="border-t border-glass-border pt-3">
              <button
                type="button"
                onClick={() => setAddOpen((v) => !v)}
                className="mb-2 flex w-full items-center justify-between rounded-lg border border-accent/35 bg-accent/10 px-3 py-2 text-sm font-medium text-accent-soft hover:bg-accent/15"
              >
                <span>Add layers</span>
                <span className="text-xs opacity-80">
                  {addableChannels.length + addableComposites.length} available
                  {addOpen ? " · −" : " · +"}
                </span>
              </button>

              {addOpen ? (
                <div className="max-h-48 space-y-3 overflow-y-auto pr-1">
                  <AddGroup
                    title={`Channels (${addableChannels.length})`}
                    products={addableChannels}
                    onAdd={addLayer}
                    pendingIds={pendingIds}
                  />
                  <AddGroup
                    title={`Composites (${addableComposites.length})`}
                    products={addableComposites}
                    onAdd={addLayer}
                    pendingIds={pendingIds}
                  />
                  {!addableChannels.length && !addableComposites.length ? (
                    <p className="text-xs text-fg-muted">
                      All generated products are already on the map.
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>

          <div className="relative min-h-[360px] overflow-hidden rounded-xl border border-glass-border sm:min-h-[480px] lg:min-h-[560px]">
            <MercatorMapCanvas
              center={center}
              zoom={mapConfig.default_zoom}
              bounds={bounds}
              layers={overlayLayers}
              showBasemap={basemapOn}
              className="z-0 h-full w-full [&_.leaflet-container]:h-full [&_.leaflet-container]:w-full [&_.leaflet-container]:rounded-xl [&_.leaflet-control-attribution]:text-[10px]"
            />

            <div className="pointer-events-none absolute left-3 top-3 rounded-md border border-glass-border bg-[var(--map-chip-bg)] px-2 py-1 text-[10px] font-medium text-fg-heading backdrop-blur-md">
              {mapConfig.projection} · Pakistan ROI
            </div>

            <div className="pointer-events-none absolute bottom-8 left-3 right-3 flex flex-wrap gap-1.5">
              {layers
                .filter((l) => l.visible && mapUrls[l.productId])
                .map((l) => {
                  const p = byId.get(l.productId);
                  if (!p) return null;
                  return (
                    <span
                      key={l.productId}
                      className="rounded-full border border-glass-border bg-[var(--map-chip-bg)] px-2 py-0.5 text-[10px] font-medium text-fg-heading backdrop-blur-md"
                    >
                      {productShortLabel(p.product_name)}
                    </span>
                  );
                })}
            </div>
          </div>
        </div>
      </GlassPanel>
    </div>
  );
}

function AddGroup({
  title,
  products,
  onAdd,
  pendingIds,
}: {
  title: string;
  products: Product[];
  onAdd: (id: number) => void;
  pendingIds: number[];
}) {
  if (!products.length) return null;
  const pending = new Set(pendingIds);
  return (
    <div>
      <p className="mb-1.5 text-[11px] uppercase tracking-[0.14em] text-fg-subtle">
        {title}
      </p>
      <ul className="space-y-1">
        {products.map((p) => {
          const busy = pending.has(p.id);
          return (
            <li key={p.id}>
              <button
                type="button"
                disabled={busy}
                onClick={() => onAdd(p.id)}
                className="flex w-full items-center justify-between gap-2 rounded-lg border border-glass-border bg-surface-panel px-2.5 py-1.5 text-left text-sm transition hover:border-accent/40 hover:bg-accent/10 disabled:opacity-60"
              >
                <span className="min-w-0 truncate">
                  <span className="font-medium text-fg-heading">
                    {productLabel(p.product_name)}
                  </span>
                  <span className="ml-1.5 font-mono text-[10px] text-fg-subtle">
                    {productShortLabel(p.product_name)}
                  </span>
                </span>
                <span className="shrink-0 text-[11px] font-medium text-accent">
                  {busy ? "…" : "+ Add"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
