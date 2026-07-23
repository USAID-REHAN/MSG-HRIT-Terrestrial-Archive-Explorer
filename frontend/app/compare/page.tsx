"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { ExplainBlock } from "@/components/ui/ExplainBlock";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  api,
  ComparePanel,
  CompareResponse,
  DateSummary,
} from "@/lib/api-client";
import { productLabel, productShortLabel } from "@/lib/product-labels";

function displayTime(hhmm: string | null | undefined): string {
  if (!hhmm) return "—";
  return hhmm.replace(/-/g, ":");
}

const ROLE_HINT: Record<string, string> = {
  daytime:
    "Near the daytime target (~09:00). Expect a mostly sunlit disk for natural colour.",
  twilight:
    "Near the twilight target (~14:00). The terminator is crossing the disk — natural colour can still look bright over Africa even while the eastern limb darkens.",
  nighttime:
    "Near the nighttime target (~20:00). Expect a dark disk for natural colour; solar channels are usually unavailable.",
};

type LightboxState = {
  src: string;
  title: string;
  subtitle: string;
};

function CompareInner() {
  const search = useSearchParams();
  const [dates, setDates] = useState<DateSummary[]>([]);
  const [date, setDate] = useState(search.get("date") || "");
  const [product, setProduct] = useState(
    search.get("product") || "natural_color"
  );
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lightbox, setLightbox] = useState<LightboxState | null>(null);

  useEffect(() => {
    api
      .dates()
      .then((rows) => {
        setDates(rows);
        if (!date && rows.length) {
          const withSample = rows.find((d) => d.sampled_count > 0) || rows[0];
          setDate(withSample.date);
        }
      })
      .catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- seed date once from catalog
  }, []);

  const load = useCallback(async () => {
    if (!date) return;
    setLoading(true);
    try {
      const res = await api.compare(date, product);
      setData(res);
      setError(null);
      setProduct((current) => {
        if (
          res.available_products.length &&
          !res.available_products.includes(current)
        ) {
          return res.available_products[0];
        }
        return current;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Compare failed");
    } finally {
      setLoading(false);
    }
  }, [date, product]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightbox(null);
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [lightbox]);

  const products = useMemo(
    () => data?.available_products || [],
    [data?.available_products]
  );

  const selectClass =
    "rounded-xl border border-glass-border bg-[#101c26] px-3 py-2 text-sm font-medium text-white shadow-sm outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/40 theme-light:bg-white theme-light:text-slate-900";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-fg-heading">
          Day / twilight / night compare
        </h1>
        <p className="mt-1 text-fg-muted">
          Same date, same product — three sample roles side by side
        </p>
      </div>

      <ExplainBlock title="Why this view exists">
        <p>
          The sample downloads one daytime, one twilight, and one nighttime
          timeslot per date. Each panel loads the product file from that
          timeslot&apos;s own folder (e.g.{" "}
          <code className="text-accent-soft">…/09-00/</code>,{" "}
          <code className="text-accent-soft">…/14-00/</code>,{" "}
          <code className="text-accent-soft">…/20-00/</code>) — not the same
          image repeated. Natural colour at 14:00 can still look fairly bright
          over Africa; the night panel at ~20:00 should look clearly darker.
        </p>
      </ExplainBlock>

      {error ? (
        <GlassPanel className="border-rose-400/40">
          <p className="text-sm text-rose-700 theme-dark:text-rose-100">{error}</p>
        </GlassPanel>
      ) : null}

      <GlassPanel>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs font-semibold uppercase tracking-wider text-fg-soft">
              Date
            </span>
            <select
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className={selectClass}
            >
              {!dates.length ? <option value="">No dates yet</option> : null}
              {dates.map((d) => (
                <option key={d.date} value={d.date}>
                  {d.date} · {d.sample_label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs font-semibold uppercase tracking-wider text-fg-soft">
              Product
            </span>
            <select
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              className={`min-w-[14rem] ${selectClass}`}
            >
              {(products.length ? products : [product]).map((name) => (
                <option key={name} value={name}>
                  {productLabel(name)}
                </option>
              ))}
            </select>
          </label>
          <Link
            href="/browse"
            className="rounded-full border border-glass-border px-3 py-2 text-sm text-fg-soft hover:bg-surface-hover"
          >
            Back to Browse
          </Link>
        </div>
        {loading ? (
          <p className="mt-3 text-sm text-fg-muted">Loading compare panels…</p>
        ) : null}
      </GlassPanel>

      <div className="grid gap-4 lg:grid-cols-3">
        {(data?.panels || []).map((panel) => (
          <CompareCard
            key={panel.role}
            panel={panel}
            date={data?.date || date}
            onOpenFull={(state) => setLightbox(state)}
          />
        ))}
        {!data?.panels?.length && !loading ? (
          <GlassPanel className="lg:col-span-3">
            <p className="text-sm text-fg-muted">
              Pick a date with sampled roles, or run discovery + sample selection
              from the dashboard first.
            </p>
          </GlassPanel>
        ) : null}
      </div>

      {lightbox ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Full resolution image"
          onClick={() => setLightbox(null)}
        >
          <div
            className="relative flex max-h-[92vh] w-full max-w-5xl flex-col gap-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-glass-border bg-[#0c141c]/95 px-4 py-3 text-white">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{lightbox.title}</p>
                <p className="truncate text-xs text-slate-300">
                  {lightbox.subtitle}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <a
                  href={lightbox.src}
                  download
                  className="rounded-full border border-white/20 px-3 py-1.5 text-xs text-white hover:bg-white/10"
                >
                  Download PNG
                </a>
                <button
                  type="button"
                  onClick={() => setLightbox(null)}
                  className="rounded-full border border-accent/50 bg-accent/20 px-3 py-1.5 text-xs font-medium text-accent-soft hover:bg-accent/30"
                >
                  Close (Esc)
                </button>
              </div>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={lightbox.src}
              alt={lightbox.title}
              className="mx-auto max-h-[78vh] w-auto max-w-full rounded-xl border border-white/10 object-contain"
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CompareCard({
  panel,
  date,
  onOpenFull,
}: {
  panel: ComparePanel;
  date: string;
  onOpenFull: (state: LightboxState) => void;
}) {
  const ts = panel.timeslot;
  const product = panel.product;
  const thumb =
    product?.availability_status === "generated"
      ? product.thumbnail_url || product.image_url
      : null;
  const hint = ROLE_HINT[panel.role] || "";

  return (
    <GlassPanel className="flex flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <StatusBadge status={panel.role} />
        {ts ? (
          <span className="text-sm font-semibold tabular-nums text-fg-heading">
            {displayTime(ts.time)} UTC
          </span>
        ) : null}
      </div>
      <p className="mb-2 text-xs text-fg-soft">
        {date}
        {ts ? (
          <>
            {" "}
            · file from{" "}
            <code className="text-accent-soft">
              {ts.date}/{ts.time}/
            </code>
          </>
        ) : null}
      </p>
      <div className="mb-3 flex flex-wrap gap-2">
        {ts ? <StatusBadge status={ts.download_status} /> : null}
        {product ? <StatusBadge status={product.availability_status} /> : null}
      </div>
      {hint ? (
        <p className="mb-3 text-xs leading-relaxed text-fg-muted">{hint}</p>
      ) : null}

      {thumb ? (
        <button
          type="button"
          onClick={() => {
            if (product?.image_url) {
              onOpenFull({
                src: product.image_url,
                title: `${productLabel(product.product_name)} · ${panel.role}`,
                subtitle: `${date} · ${displayTime(ts?.time)} UTC · timeslot #${ts?.id}`,
              });
            }
          }}
          className="group relative block w-full overflow-hidden rounded-xl border border-glass-border text-left"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={thumb}
            alt={`${panel.role} ${productShortLabel(product?.product_name || "")} ${displayTime(ts?.time)}`}
            className="aspect-square w-full object-cover transition group-hover:opacity-90"
          />
        </button>
      ) : (
        <div className="flex aspect-square items-center justify-center rounded-xl border border-dashed border-glass-border bg-surface-panel/60 p-4 text-center text-sm text-fg-muted">
          {panel.missing_reason ||
            (product?.availability_status === "unavailable_night"
              ? "Unavailable at night — solar channel / daylight composite"
              : product?.availability_status === "unavailable_error"
                ? product.error_message || "Processing error"
                : "No image")}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {ts ? (
          <Link
            href={`/timeslot/${ts.id}`}
            className="rounded-full border border-glass-border px-3 py-1.5 text-xs text-fg-soft hover:bg-surface-hover"
          >
            Open timeslot
          </Link>
        ) : null}
        {product?.image_url && product.availability_status === "generated" ? (
          <button
            type="button"
            onClick={() =>
              onOpenFull({
                src: product.image_url!,
                title: `${productLabel(product.product_name)} · ${panel.role}`,
                subtitle: `${date} · ${displayTime(ts?.time)} UTC · timeslot #${ts?.id}`,
              })
            }
            className="rounded-full border border-glass-border px-3 py-1.5 text-xs text-fg-soft hover:bg-surface-hover"
          >
            Full resolution
          </button>
        ) : null}
      </div>
    </GlassPanel>
  );
}

export default function ComparePage() {
  return (
    <Suspense
      fallback={
        <GlassPanel>
          <p className="text-sm text-fg-muted">Loading compare view…</p>
        </GlassPanel>
      }
    >
      <CompareInner />
    </Suspense>
  );
}
