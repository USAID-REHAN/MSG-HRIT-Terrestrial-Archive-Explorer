"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { CesiumGlobeOverlayDescriptor } from "@/components/CesiumGlobeCanvas";
import {
  api,
  type DateSummary,
  type GlobeProduct,
  type Timeslot,
} from "@/lib/api-client";
import { productLabel, sortProductsByKind } from "@/lib/product-labels";

const CesiumGlobeCanvas = dynamic(
  () =>
    import("@/components/CesiumGlobeCanvas").then(
      (module) => module.CesiumGlobeCanvas,
    ),
  { ssr: false },
);

type GlobeWorkspaceProps = {
  timeslotId?: number;
};

function message(value: unknown): string {
  return value instanceof Error ? value.message : String(value);
}

function displayTime(value: string): string {
  return value.replaceAll("-", ":");
}

function statusLabel(status: GlobeProduct["generation_status"]): string {
  switch (status) {
    case "not_generated":
      return "Ready to generate";
    case "unavailable_night":
      return "Unavailable at night";
    default:
      return status.replaceAll("_", " ");
  }
}

function validOverlay(product: GlobeProduct): CesiumGlobeOverlayDescriptor | null {
  const bounds = product.metadata?.bounds;
  if (
    product.generation_status !== "ready" ||
    !product.image_url ||
    !bounds ||
    ![bounds.west, bounds.south, bounds.east, bounds.north].every(Number.isFinite) ||
    bounds.west >= bounds.east ||
    bounds.south >= bounds.north
  ) {
    return null;
  }
  return {
    id: String(product.product_id),
    imageUrl: product.image_url,
    west: bounds.west,
    south: bounds.south,
    east: bounds.east,
    north: bounds.north,
    visible: true,
    active: false,
  };
}

export function GlobeWorkspace({ timeslotId: exactTimeslotId }: GlobeWorkspaceProps) {
  const [dates, setDates] = useState<DateSummary[]>([]);
  const [selectedDate, setSelectedDate] = useState("");
  const [timeslots, setTimeslots] = useState<Timeslot[]>([]);
  const [selectedTimeslotId, setSelectedTimeslotId] = useState<number | null>(
    exactTimeslotId ?? null,
  );
  const [timeslot, setTimeslot] = useState<Timeslot | null>(null);
  const [products, setProducts] = useState<GlobeProduct[]>([]);
  const [appliedIds, setAppliedIds] = useState<number[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [hiddenIds, setHiddenIds] = useState<Set<number>>(new Set());
  const [collapsedIds, setCollapsedIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isExactRoute = exactTimeslotId != null;

  const updateProduct = useCallback((next: GlobeProduct) => {
    setProducts((current) =>
      current.map((product) =>
        product.product_id === next.product_id ? next : product,
      ),
    );
  }, []);

  useEffect(() => {
    if (isExactRoute) return;
    let cancelled = false;
    api
      .dates()
      .then((availableDates) => {
        if (cancelled) return;
        setDates(availableDates);
        setSelectedDate((current) => current || availableDates.at(-1)?.date || "");
      })
      .catch((value) => !cancelled && setError(message(value)));
    return () => {
      cancelled = true;
    };
  }, [isExactRoute]);

  useEffect(() => {
    if (isExactRoute || !selectedDate) return;
    let cancelled = false;
    setLoading(true);
    api
      .timeslots({ date: selectedDate, sampled_only: true })
      .then((availableTimeslots) => {
        if (cancelled) return;
        const withProducts = availableTimeslots.filter(
          (item) => (item.products_generated ?? 0) > 0,
        );
        setTimeslots(withProducts);
        setSelectedTimeslotId((current) =>
          withProducts.some((item) => item.id === current)
            ? current
            : (withProducts[0]?.id ?? null),
        );
        if (!withProducts.length) {
          setTimeslot(null);
          setProducts([]);
          setLoading(false);
        }
      })
      .catch((value) => {
        if (!cancelled) {
          setError(message(value));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isExactRoute, selectedDate]);

  useEffect(() => {
    if (!selectedTimeslotId) {
      if (isExactRoute) setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      api.timeslot(selectedTimeslotId),
      api.globeCatalog(selectedTimeslotId),
    ])
      .then(([timeslotResponse, catalog]) => {
        if (cancelled) return;
        setTimeslot(timeslotResponse.timeslot);
        setProducts(catalog.products.filter((product) => product.reference != null));
        setAppliedIds([]);
        setActiveId(null);
        setHiddenIds(new Set());
        setCollapsedIds(new Set());
      })
      .catch((value) => !cancelled && setError(message(value)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [isExactRoute, selectedTimeslotId]);

  const startLayer = useCallback(
    async (product: GlobeProduct) => {
      setAppliedIds((current) =>
        current.includes(product.product_id)
          ? current
          : [...current, product.product_id],
      );
      setActiveId(product.product_id);
      setCollapsedIds((current) => {
        const next = new Set(current);
        next.add(product.product_id);
        return next;
      });
      setHiddenIds((current) => {
        const next = new Set(current);
        next.delete(product.product_id);
        return next;
      });
      if (!["not_generated", "error", "busy"].includes(product.generation_status)) {
        return;
      }
      updateProduct({ ...product, generation_status: "generating", error: null });
      try {
        updateProduct(await api.generateGlobeProduct(product.product_id));
      } catch (value) {
        updateProduct({
          ...product,
          generation_status: "error",
          error: message(value),
        });
      }
    },
    [updateProduct],
  );

  const removeLayer = useCallback((productId: number) => {
    setAppliedIds((current) => {
      const next = current.filter((id) => id !== productId);
      setActiveId((active) =>
        active === productId ? (next.at(-1) ?? null) : active,
      );
      return next;
    });
    setHiddenIds((current) => {
      const next = new Set(current);
      next.delete(productId);
      return next;
    });
    setCollapsedIds((current) => {
      const next = new Set(current);
      next.delete(productId);
      return next;
    });
  }, []);

  const generatingIds = useMemo(
    () =>
      products
        .filter(
          (product) =>
            appliedIds.includes(product.product_id) &&
            product.generation_status === "generating",
        )
        .map((product) => product.product_id),
    [appliedIds, products],
  );

  useEffect(() => {
    if (!generatingIds.length) return;
    let cancelled = false;
    let running = false;
    let pointerDown = false;
    const onDown = () => {
      pointerDown = true;
    };
    const onUp = () => {
      pointerDown = false;
    };
    const poll = async () => {
      if (running || pointerDown || document.visibilityState === "hidden") return;
      running = true;
      const results = await Promise.allSettled(
        generatingIds.map((id) => api.globeProductStatus(id)),
      );
      if (!cancelled) {
        results.forEach((result) => {
          if (result.status === "fulfilled") updateProduct(result.value);
        });
      }
      running = false;
    };
    window.addEventListener("pointerdown", onDown, true);
    window.addEventListener("pointerup", onUp, true);
    window.addEventListener("pointercancel", onUp, true);
    const timer = window.setInterval(() => void poll(), 1500);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("pointerup", onUp, true);
      window.removeEventListener("pointercancel", onUp, true);
    };
  }, [generatingIds, updateProduct]);

  const appliedProducts = useMemo(
    () =>
      appliedIds
        .map((id) => products.find((product) => product.product_id === id))
        .filter((product): product is GlobeProduct => product != null),
    [appliedIds, products],
  );

  const overlays = useMemo(
    () =>
      appliedProducts.flatMap((product) => {
        const overlay = validOverlay(product);
        return overlay
          ? [
              {
                ...overlay,
                visible: !hiddenIds.has(product.product_id),
                active: product.product_id === activeId,
              },
            ]
          : [];
      }),
    [activeId, appliedProducts, hiddenIds],
  );

  const groupedProducts = useMemo(() => {
    const sorted = sortProductsByKind(products);
    return {
      channels: sorted.filter((product) => product.product_kind === "channel"),
      composites: sorted.filter((product) => product.product_kind === "composite"),
    };
  }, [products]);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-accent/80">
            Interactive layers
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-fg-heading">
            Globe workspace
          </h1>
          <p className="mt-1 text-sm text-fg-muted">
            {timeslot
              ? `${timeslot.date} · ${displayTime(timeslot.time)}`
              : "Choose existing processed data to begin."}
          </p>
        </div>
        {isExactRoute ? (
          <div className="flex flex-wrap gap-2">
            <Link
              href="/globe"
              className="rounded-full border border-glass-border px-3 py-1.5 text-sm text-fg-soft hover:bg-surface-hover"
            >
              Choose another timeslot
            </Link>
            {timeslot ? (
              <Link
                href={`/timeslot/${timeslot.id}`}
                className="rounded-full border border-accent/40 bg-accent/10 px-3 py-1.5 text-sm text-accent-soft hover:bg-accent/20"
              >
                View timeslot details
              </Link>
            ) : null}
          </div>
        ) : (
          <div className="grid w-full gap-2 sm:w-auto sm:grid-cols-2">
            <label className="text-xs text-fg-muted">
              Date
              <select
                value={selectedDate}
                onChange={(event) => setSelectedDate(event.target.value)}
                className="mt-1 block min-h-11 w-full rounded-xl border px-3 text-sm sm:min-w-40"
              >
                {dates.map((date) => (
                  <option key={date.date} value={date.date}>
                    {date.date}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-fg-muted">
              Timeslot
              <select
                value={selectedTimeslotId ?? ""}
                onChange={(event) =>
                  setSelectedTimeslotId(
                    event.target.value ? Number(event.target.value) : null,
                  )
                }
                className="mt-1 block min-h-11 w-full rounded-xl border px-3 text-sm sm:min-w-52"
                disabled={!timeslots.length}
              >
                {!timeslots.length ? <option value="">No processed sample</option> : null}
                {timeslots.map((item) => (
                  <option key={item.id} value={item.id}>
                    {displayTime(item.time)}
                    {item.sample_role ? ` · ${item.sample_role}` : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 theme-dark:text-rose-100"
        >
          {error}
        </div>
      ) : null}

      <section className="relative left-1/2 w-screen -translate-x-1/2 overflow-hidden border-y border-glass-border bg-[#061820] shadow-2xl">
        <div className="relative h-[72svh] min-h-[34rem] max-h-[58rem]">
          <CesiumGlobeCanvas
            overlays={overlays}
            ariaLabel={`Interactive 3D Earth${timeslot ? ` for ${timeslot.date} at ${displayTime(timeslot.time)}` : ""}`}
            onError={(value) => setError(value.message)}
          />

          <details className="group absolute left-3 top-3 z-20 w-[min(22rem,calc(100%-1.5rem))] rounded-2xl border border-white/15 bg-slate-950/85 text-slate-100 shadow-2xl backdrop-blur-xl sm:left-5 sm:top-5">
            <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 font-medium">
              <span>Layers ({appliedIds.length} applied)</span>
              <span aria-hidden="true" className="text-teal-300">
                ＋
              </span>
            </summary>
            <div className="max-h-[min(58svh,32rem)] overflow-y-auto border-t border-white/10 p-2">
              {loading ? (
                <p className="px-3 py-4 text-sm text-slate-300" role="status">
                  Loading available layers…
                </p>
              ) : !products.length ? (
                <p className="px-3 py-4 text-sm text-slate-300">
                  No globe-eligible products with canonical reference data are
                  available for this timeslot.
                </p>
              ) : (
                <>
                  <LayerMenuGroup
                    title="Channels"
                    products={groupedProducts.channels}
                    appliedIds={appliedIds}
                    onToggle={(product) =>
                      appliedIds.includes(product.product_id)
                        ? removeLayer(product.product_id)
                        : void startLayer(product)
                    }
                  />
                  <LayerMenuGroup
                    title="Composites"
                    products={groupedProducts.composites}
                    appliedIds={appliedIds}
                    onToggle={(product) =>
                      appliedIds.includes(product.product_id)
                        ? removeLayer(product.product_id)
                        : void startLayer(product)
                    }
                  />
                </>
              )}
            </div>
          </details>

          {!appliedProducts.length && !loading ? (
            <div className="pointer-events-none absolute inset-x-4 top-1/2 z-10 -translate-y-1/2 text-center">
              <p className="mx-auto max-w-md rounded-2xl bg-slate-950/70 px-5 py-4 text-sm text-slate-200 backdrop-blur-md">
                Open Layers and apply any combination of channels or composites.
              </p>
            </div>
          ) : null}

          <div
            className="absolute inset-x-0 bottom-0 z-20 flex snap-x items-end gap-3 overflow-x-auto p-3 pb-4 sm:p-5"
            aria-label="Applied layer details"
          >
            {appliedProducts.map((product) => (
              <LayerPanel
                key={product.product_id}
                product={product}
                active={activeId === product.product_id}
                hidden={hiddenIds.has(product.product_id)}
                collapsed={collapsedIds.has(product.product_id)}
                onActivate={() => setActiveId(product.product_id)}
                onToggleVisibility={() =>
                  setHiddenIds((current) => {
                    const next = new Set(current);
                    if (next.has(product.product_id)) next.delete(product.product_id);
                    else next.add(product.product_id);
                    return next;
                  })
                }
                onToggleCollapsed={() =>
                  setCollapsedIds((current) => {
                    const next = new Set(current);
                    if (next.has(product.product_id)) next.delete(product.product_id);
                    else next.add(product.product_id);
                    return next;
                  })
                }
                onRemove={() => removeLayer(product.product_id)}
                onRetry={() => void startLayer(product)}
              />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function LayerMenuGroup({
  title,
  products,
  appliedIds,
  onToggle,
}: {
  title: string;
  products: GlobeProduct[];
  appliedIds: number[];
  onToggle: (product: GlobeProduct) => void;
}) {
  if (!products.length) return null;
  return (
    <fieldset className="mb-3 last:mb-0">
      <legend className="px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-teal-300">
        {title}
      </legend>
      <div className="space-y-1">
        {products.map((product) => {
          const applied = appliedIds.includes(product.product_id);
          return (
            <label
              key={product.product_id}
              className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-3 py-2 hover:bg-white/10"
            >
              <input
                type="checkbox"
                checked={applied}
                onChange={() => onToggle(product)}
                className="h-4 w-4 accent-teal-400"
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">
                  {productLabel(product.product_name)}
                </span>
                <span className="block truncate font-mono text-[10px] text-slate-400">
                  {product.product_name}
                </span>
              </span>
              <LayerStatus product={product} compact />
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function LayerStatus({
  product,
  compact = false,
}: {
  product: GlobeProduct;
  compact?: boolean;
}) {
  const status = product.generation_status;
  const colors =
    status === "ready"
      ? "border-emerald-400/40 bg-emerald-400/15 text-emerald-200"
      : status === "generating"
        ? "border-sky-400/40 bg-sky-400/15 text-sky-200"
        : status === "unavailable_night"
          ? "border-amber-400/40 bg-amber-400/15 text-amber-200"
          : status === "error" || status === "busy"
            ? "border-rose-400/40 bg-rose-400/15 text-rose-200"
            : "border-slate-400/30 bg-slate-400/10 text-slate-300";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize ${colors}`}
    >
      {status === "generating" ? (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      ) : null}
      {compact && status === "not_generated" ? "available" : statusLabel(status)}
    </span>
  );
}

function LayerPanel({
  product,
  active,
  hidden,
  collapsed,
  onActivate,
  onToggleVisibility,
  onToggleCollapsed,
  onRemove,
  onRetry,
}: {
  product: GlobeProduct;
  active: boolean;
  hidden: boolean;
  collapsed: boolean;
  onActivate: () => void;
  onToggleVisibility: () => void;
  onToggleCollapsed: () => void;
  onRemove: () => void;
  onRetry: () => void;
}) {
  const reference = product.reference;
  if (!reference) return null;
  return (
    <article
      className={[
        "pointer-events-auto flex w-[min(88vw,22rem)] max-h-[min(32svh,14rem)] shrink-0 snap-start flex-col rounded-2xl border bg-slate-950/90 text-slate-100 shadow-2xl backdrop-blur-xl transition",
        active
          ? "border-teal-300/80 ring-2 ring-teal-300/20"
          : "border-white/15",
      ].join(" ")}
      onClick={onActivate}
      aria-current={active ? "true" : undefined}
    >
      <div className="flex shrink-0 items-center gap-1.5 px-2.5 py-1.5">
        <button
          type="button"
          onClick={onActivate}
          className="min-w-0 flex-1 text-left"
          aria-label={`Activate ${productLabel(product.product_name)} layer`}
        >
          <span className="block truncate text-sm font-semibold">
            {productLabel(product.product_name)}
          </span>
          <span className="block truncate font-mono text-[10px] text-slate-400">
            {reference.product_name}
          </span>
        </button>
        <LayerStatus product={product} />
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onToggleVisibility();
          }}
          disabled={product.generation_status !== "ready"}
          className="min-h-9 rounded-lg px-2 text-xs text-slate-200 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
          aria-pressed={!hidden}
          aria-label={`${hidden ? "Show" : "Hide"} ${productLabel(product.product_name)}`}
        >
          {hidden ? "Show" : "Hide"}
        </button>
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onToggleCollapsed();
          }}
          className="min-h-9 rounded-lg px-2 text-xs text-slate-200 hover:bg-white/10"
          aria-expanded={!collapsed}
          aria-label={`${collapsed ? "Expand" : "Collapse"} ${productLabel(product.product_name)} details`}
        >
          {collapsed ? "Expand" : "Collapse"}
        </button>
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onRemove();
          }}
          className="min-h-9 rounded-lg px-2 text-xs text-rose-200 hover:bg-rose-400/15"
          aria-label={`Remove ${productLabel(product.product_name)} layer`}
        >
          Remove
        </button>
      </div>

      {!collapsed ? (
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain border-t border-white/10 px-3 py-2 text-[11px] leading-snug text-slate-300">
          {product.generation_status === "generating" ? (
            <p role="status" className="mb-3 rounded-lg bg-sky-400/10 p-2 text-sky-100">
              Generating this globe layer. It will appear automatically when ready.
            </p>
          ) : product.generation_status === "unavailable_night" ? (
            <p className="mb-3 rounded-lg bg-amber-400/10 p-2 text-amber-100">
              Unavailable at night: {product.error || "this product requires sunlight."}
            </p>
          ) : product.generation_status === "error" ||
            product.generation_status === "busy" ? (
            <div role="alert" className="mb-3 rounded-lg bg-rose-400/10 p-2 text-rose-100">
              <p>{product.error || "Globe layer generation failed."}</p>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onRetry();
                }}
                className="mt-2 rounded-full border border-rose-300/40 px-3 py-1 font-medium hover:bg-rose-300/10"
              >
                Retry generation
              </button>
            </div>
          ) : product.generation_status === "not_generated" ? (
            <p role="status" className="mb-3 rounded-lg bg-slate-400/10 p-2">
              Waiting to start generation…
            </p>
          ) : null}

          <dl className="space-y-2">
            <div>
              <dt className="font-semibold uppercase tracking-wide text-teal-300">
                Color / feature interpretation
              </dt>
              <dd className="mt-1 text-sm text-slate-100">
                {reference.plain_language_description}
              </dd>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <dt className="text-slate-400">Wavelength / recipe</dt>
                <dd className="mt-0.5 text-slate-100">
                  {reference.wavelength_or_spectral_band}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">Resolution</dt>
                <dd className="mt-0.5 text-slate-100">
                  {reference.approximate_resolution}
                </dd>
              </div>
            </div>
            <ApplicationNote
              title="Agriculture"
              text={reference.agriculture_application}
            />
            <ApplicationNote title="Aviation" text={reference.aviation_application} />
            <ApplicationNote
              title="Natural resources"
              text={reference.natural_resource_application}
            />
            <ApplicationNote
              title="Disaster response"
              text={reference.disaster_response_application}
            />
          </dl>
        </div>
      ) : null}
    </article>
  );
}

function ApplicationNote({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <dt className="font-medium text-slate-200">{title} · why it matters</dt>
      <dd className="mt-0.5">{text}</dd>
    </div>
  );
}
