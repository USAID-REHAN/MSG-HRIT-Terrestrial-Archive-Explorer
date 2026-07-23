"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { DynamicImageViewer } from "@/components/DynamicImageViewer";
import { ExplainBlock } from "@/components/ui/ExplainBlock";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api, Product, Timeslot } from "@/lib/api-client";
import { productDomainExample } from "@/lib/product-domain-examples";
import {
  productLabel,
  productShortLabel,
  sortProductsByKind,
} from "@/lib/product-labels";

export default function TimeslotPage() {
  const params = useParams();
  const id = Number(params.id);
  const [timeslot, setTimeslot] = useState<Timeslot | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [siblings, setSiblings] = useState<Timeslot[]>([]);
  const [active, setActive] = useState<Product | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .timeslot(id)
      .then((data) => {
        setTimeslot(data.timeslot);
        setProducts(data.products);
        setSiblings(data.siblings);
        setActive(null);
      })
      .catch((e) => setError(e.message));
  }, [id]);

  const channels = useMemo(
    () => sortProductsByKind(products.filter((p) => p.product_kind === "channel")),
    [products]
  );
  const composites = useMemo(
    () =>
      sortProductsByKind(products.filter((p) => p.product_kind === "composite")),
    [products]
  );

  const prevNext = useMemo(() => {
    const idx = siblings.findIndex((s) => s.id === id);
    return {
      prev: idx > 0 ? siblings[idx - 1] : null,
      next: idx >= 0 && idx < siblings.length - 1 ? siblings[idx + 1] : null,
    };
  }, [siblings, id]);

  return (
    <div className="space-y-6">
      {error ? (
        <GlassPanel className="border-rose-400/40">
          <p className="text-sm text-rose-700 theme-dark:text-rose-100">{error}</p>
        </GlassPanel>
      ) : null}

      {timeslot ? (
        <>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-fg-subtle">
                Timeslot
              </p>
              <h1 className="text-3xl font-semibold text-fg-heading">
                {timeslot.date} · {timeslot.time.replace(/-/g, ":")}
              </h1>
              <div className="mt-2 flex flex-wrap gap-2">
                {timeslot.sample_role ? (
                  <StatusBadge status={timeslot.sample_role} />
                ) : null}
                {timeslot.sample_match === "nearest_fallback" ? (
                  <span className="rounded-md border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-amber-800 theme-dark:text-amber-200">
                    Nearest available
                  </span>
                ) : null}
                <StatusBadge status={timeslot.download_status} />
              </div>
              {timeslot.sample_note ? (
                <p className="mt-3 max-w-2xl text-sm leading-relaxed text-fg-muted">
                  {timeslot.sample_note}
                </p>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Link
                href={`/timeslot/${timeslot.id}/globe`}
                className="rounded-full border border-accent/40 bg-accent/10 px-3 py-1.5 text-sm text-accent-soft hover:bg-accent/20"
              >
                Open in 3D Globe
              </Link>
              {prevNext.prev ? (
                <Link
                  href={`/timeslot/${prevNext.prev.id}`}
                  className="rounded-full border border-glass-border px-3 py-1.5 text-sm text-fg-soft hover:bg-surface-hover"
                >
                  ← {prevNext.prev.sample_role || prevNext.prev.time}
                </Link>
              ) : null}
              {prevNext.next ? (
                <Link
                  href={`/timeslot/${prevNext.next.id}`}
                  className="rounded-full border border-glass-border px-3 py-1.5 text-sm text-fg-soft hover:bg-surface-hover"
                >
                  {prevNext.next.sample_role || prevNext.next.time} →
                </Link>
              ) : null}
            </div>
          </div>

          <ExplainBlock title="Day / night contrast">
            <p>
              Use the previous/next links to jump between this date&apos;s daytime,
              twilight, and nighttime samples — or open the{" "}
              <Link
                href={`/compare?date=${encodeURIComponent(timeslot.date)}`}
                className="text-accent-soft underline-offset-2 hover:underline"
              >
                side-by-side compare view
              </Link>{" "}
              for the same product across all three roles. Solar channels (HRV,
              VIS006, VIS008, IR_016) and daylight-dependent composites (natural
              colour, overview, day microphysics, HRV products, etc.) are expected
              to be <em>unavailable at night</em> — that is physics, not a
              processing failure. Full-disk gallery images are oriented north-up
              (Europe/Russia toward the top, Antarctica toward the bottom).
            </p>
          </ExplainBlock>

          {!products.length ? (
            <GlassPanel>
              <p className="text-sm text-fg-muted">
                No products yet. Download this timeslot, then run processing from
                the dashboard.
              </p>
              {timeslot.download_status === "failed" ? (
                <button
                  type="button"
                  className="mt-3 rounded-full bg-accent/90 px-4 py-2 text-sm font-medium text-ink-950"
                  onClick={() => api.retryDownload(timeslot.id)}
                >
                  Retry download
                </button>
              ) : null}
            </GlassPanel>
          ) : null}

          <Section title="Channels" products={channels} onSelect={setActive} />
          <Section
            title={`Composites (${composites.length})`}
            products={composites}
            onSelect={setActive}
          />

          <DynamicImageViewer products={products} />

          {active ? (
            <ProductDetail
              product={active}
              onClose={() => setActive(null)}
              onRetry={() => api.retryProcessing(timeslot.id)}
            />
          ) : null}
        </>
      ) : (
        <p className="text-fg-muted">Loading…</p>
      )}
    </div>
  );
}

function Section({
  title,
  products,
  onSelect,
}: {
  title: string;
  products: Product[];
  onSelect: (p: Product) => void;
}) {
  if (!products.length) return null;
  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold text-accent-soft">{title}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {products.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onSelect(p)}
            className="text-left"
          >
            <GlassPanel hover padding="sm" className="h-full">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="min-w-0">
                  <span className="block truncate font-medium text-fg-heading">
                    {productLabel(p.product_name)}
                  </span>
                  <span className="font-mono text-[10px] text-fg-subtle">
                    {productShortLabel(p.product_name)}
                  </span>
                </span>
                <StatusBadge status={p.availability_status} />
              </div>
              {p.availability_status === "generated" && p.thumbnail_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={p.thumbnail_url}
                  alt={productLabel(p.product_name)}
                  className="aspect-square w-full rounded-lg object-cover"
                />
              ) : p.availability_status === "unavailable_night" ? (
                <div className="flex aspect-square items-center justify-center rounded-lg border border-amber-400/25 bg-amber-500/5 p-4 text-center text-sm text-amber-800 theme-dark:text-amber-100/90">
                  No sunlight on the imaged disk for this timeslot — solar /
                  dependent product is expectedly empty.
                </div>
              ) : (
                <div className="flex aspect-square items-center justify-center rounded-lg border border-rose-400/25 bg-rose-500/5 p-4 text-center text-sm text-rose-700 theme-dark:text-rose-100/90">
                  {p.error_message || "Unavailable"}
                </div>
              )}
            </GlassPanel>
          </button>
        ))}
      </div>
    </div>
  );
}

function ProductDetail({
  product,
  onClose,
  onRetry,
}: {
  product: Product;
  onClose: () => void;
  onRetry: () => void;
}) {
  const ref = product.reference;
  const primaryImage = product.image_url || product.thumbnail_url || null;
  const [imageSrc, setImageSrc] = useState(primaryImage);

  useEffect(() => {
    setImageSrc(product.image_url || product.thumbnail_url || null);
  }, [product.id, product.image_url, product.thumbnail_url]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-4 backdrop-blur-sm sm:items-center"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="max-h-[90vh] w-full max-w-5xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <GlassPanel className="max-h-[90vh] overflow-auto" padding="lg">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold text-fg-heading">
              {productLabel(product.product_name)}
            </h2>
            <p className="mt-0.5 font-mono text-xs text-fg-subtle">
              {productShortLabel(product.product_name)}
            </p>
            <div className="mt-1">
              <StatusBadge status={product.availability_status} />
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-glass-border px-3 py-1 text-sm text-fg-soft hover:bg-surface-hover"
          >
            Close
          </button>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            {product.availability_status === "generated" && imageSrc ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={imageSrc}
                alt={productLabel(product.product_name)}
                className="w-full rounded-xl border border-glass-border"
                onError={() => {
                  if (imageSrc !== product.thumbnail_url && product.thumbnail_url) {
                    setImageSrc(product.thumbnail_url);
                    return;
                  }
                  setImageSrc(null);
                }}
              />
            ) : product.availability_status === "unavailable_night" ? (
              <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 p-6 text-amber-900 theme-dark:text-amber-50">
                <p className="font-medium">Unavailable because it is night</p>
                <p className="mt-2 text-sm text-amber-800 theme-dark:text-amber-100/90">
                  This product needs reflected sunlight (or solar channels as
                  inputs). For this timeslot the imaged region is in darkness,
                  so there is no valid signal — the pipeline recorded that
                  deliberately instead of treating it as an error.
                </p>
              </div>
            ) : product.availability_status === "generated" ? (
              <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 p-6 text-amber-900 theme-dark:text-amber-50">
                <p className="font-medium">Preview unavailable</p>
                <p className="mt-2 text-sm text-amber-800 theme-dark:text-amber-100/90">
                  This product was generated, but the full-size image could not be
                  loaded. The card thumbnail may still be available while the
                  larger asset finishes writing or if the original file is
                  missing.
                </p>
              </div>
            ) : (
              <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 p-6 text-rose-900 theme-dark:text-rose-50">
                <p className="font-medium">Processing error</p>
                <p className="mt-2 text-sm">{product.error_message}</p>
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-4 rounded-full bg-accent/90 px-4 py-2 text-sm font-medium text-ink-950"
                >
                  Retry processing for this timeslot
                </button>
              </div>
            )}
          </div>

          <div className="space-y-4 text-sm leading-relaxed text-fg-soft">
            {ref ? (
              <>
                <p>
                  <span className="text-fg-subtle">Band / recipe · </span>
                  {ref.wavelength_or_spectral_band}
                </p>
                <p>
                  <span className="text-fg-subtle">Resolution · </span>
                  {ref.approximate_resolution}
                </p>
                <p className="text-[15px] text-fg">
                  {ref.plain_language_description}
                </p>
                <div className="grid gap-3">
                  <AppNote
                    title="Agriculture"
                    text={ref.agriculture_application}
                    example={productDomainExample(product.product_name, "agriculture")}
                  />
                  <AppNote
                    title="Aviation"
                    text={ref.aviation_application}
                    example={productDomainExample(product.product_name, "aviation")}
                  />
                  <AppNote
                    title="Natural resources"
                    text={ref.natural_resource_application}
                    example={productDomainExample(
                      product.product_name,
                      "natural_resources"
                    )}
                  />
                  <AppNote
                    title="Disaster response"
                    text={ref.disaster_response_application}
                    example={productDomainExample(
                      product.product_name,
                      "disaster_response"
                    )}
                  />
                </div>
              </>
            ) : (
              <p>No reference text loaded for this product.</p>
            )}
          </div>
        </div>
      </GlassPanel>
      </div>
    </div>
  );
}

function AppNote({
  title,
  text,
  example,
}: {
  title: string;
  text: string;
  example: string;
}) {
  return (
    <div className="rounded-xl border border-glass-border bg-surface-panel p-3">
      <div className="text-[11px] uppercase tracking-[0.14em] text-accent/80">
        {title}
      </div>
      <p className="mt-1 text-fg-soft">{text}</p>
      <p className="mt-2 border-t border-glass-border pt-2 text-fg-muted">
        {example}
      </p>
    </div>
  );
}
