"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ExplainBlock } from "@/components/ui/ExplainBlock";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api, FinalGlobeItem, FinalGlobeListResponse } from "@/lib/api-client";
import { usePolling } from "@/lib/usePolling";

function displayTime(hhmm: string | null | undefined): string {
  if (!hhmm) return "—";
  return hhmm.replace(/-/g, ":");
}

export default function FinalGlobesPage() {
  const [data, setData] = useState<FinalGlobeListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lightbox, setLightbox] = useState<FinalGlobeItem | null>(null);
  const [roleFilter, setRoleFilter] = useState<string>("all");

  const refresh = useCallback(async () => {
    try {
      const res = await api.finalGlobes();
      setData(res);
      setError(null);
      setBusy(!!res.generate_running);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load Final Globes");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  usePolling(refresh, 2500, busy);

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

  async function generateAll(force = false) {
    setBusy(true);
    try {
      const r = await api.generateFinalGlobes(force);
      if (!r.ok) setError(r.error || "Could not start Final Globe Mix generation");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed");
      setBusy(false);
    }
  }

  const items = useMemo(() => {
    const list = data?.items || [];
    if (roleFilter === "all") return list;
    return list.filter((i) => i.sample_role === roleFilter);
  }, [data?.items, roleFilter]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-fg-subtle">
            Summary products
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-fg-heading">
            Final Globes
          </h1>
          <p className="mt-1 max-w-2xl text-fg-muted">
            {data?.product_label || "Final Globe Mix"} — one role-aware whole-disk
            mix per sampled timeslot (day / twilight / night look different)
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => generateAll(false)}
            className="rounded-full border border-accent/50 bg-accent/15 px-4 py-2 text-sm font-medium text-accent-soft hover:bg-accent/25 disabled:opacity-60"
          >
            {busy ? "Generating…" : "Generate missing globes"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => generateAll(true)}
            className="rounded-full border border-glass-border px-4 py-2 text-sm text-fg-soft hover:bg-surface-hover disabled:opacity-60"
          >
            Rebuild all
          </button>
        </div>
      </div>

      <ExplainBlock title="What is a Final Globe Mix?">
        <p>
          Each card is a <strong className="text-fg-heading">Final Globe Mix</strong>{" "}
          for one downloaded sample timeslot. A role-matched hero product (natural
          colour by day, airmass at twilight, IR / night microphysics at night) is
          blended with a few accents from that same timeslot. This does not replace
          individual products — it is a presentation overview.
        </p>
        <p>
          You get up to <strong className="text-fg-heading">39 distinct globes</strong>{" "}
          (one per sample timeslot). Daytime, twilight, and nighttime cards are
          meant to look clearly different.
        </p>
      </ExplainBlock>

      {error ? (
        <GlassPanel className="border-rose-400/40">
          <p className="text-sm text-rose-700 theme-dark:text-rose-100">{error}</p>
        </GlassPanel>
      ) : null}

      <GlassPanel>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-fg-soft">
            {data
              ? `${data.generated_count} / ${data.total} Final Globe Mix images ready`
              : "Loading…"}
            {busy ? " · generation running in background" : ""}
          </p>
          <label className="flex items-center gap-2 text-sm text-fg-soft">
            <span className="text-xs uppercase tracking-wider text-fg-subtle">
              Role
            </span>
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="rounded-xl border border-glass-border bg-[#101c26] px-3 py-1.5 text-white theme-light:bg-white theme-light:text-slate-900"
            >
              <option value="all">All roles</option>
              <option value="daytime">Daytime</option>
              <option value="twilight">Twilight</option>
              <option value="nighttime">Nighttime</option>
            </select>
          </label>
        </div>
      </GlassPanel>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <GlassPanel key={item.timeslot_id} className="flex flex-col">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-fg-heading">
                {item.date} · {displayTime(item.time)} UTC
              </span>
              {item.sample_role ? <StatusBadge status={item.sample_role} /> : null}
              <StatusBadge
                status={
                  item.status === "generated"
                    ? "generated"
                    : item.status === "error"
                      ? "failed"
                      : "queued"
                }
              />
            </div>
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-accent-soft">
              Final Globe Mix
            </p>

            {item.status === "generated" && item.thumbnail_url ? (
              <button
                type="button"
                onClick={() => setLightbox(item)}
                className="group overflow-hidden rounded-xl border border-glass-border"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={item.thumbnail_url}
                  alt={`Final Globe Mix ${item.date} ${displayTime(item.time)}`}
                  className="aspect-square w-full object-cover transition group-hover:opacity-90"
                />
              </button>
            ) : (
              <div className="flex aspect-square items-center justify-center rounded-xl border border-dashed border-glass-border bg-surface-panel/50 p-4 text-center text-sm text-fg-muted">
                {item.status === "error"
                  ? item.error_message || "Generation error"
                  : busy
                    ? "Waiting for Final Globe Mix…"
                    : "Not generated yet — click Generate missing globes"}
              </div>
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              <Link
                href={`/timeslot/${item.timeslot_id}`}
                className="rounded-full border border-glass-border px-3 py-1.5 text-xs text-fg-soft hover:bg-surface-hover"
              >
                Open timeslot
              </Link>
              {item.status === "generated" && item.image_url ? (
                <button
                  type="button"
                  onClick={() => setLightbox(item)}
                  className="rounded-full border border-glass-border px-3 py-1.5 text-xs text-fg-soft hover:bg-surface-hover"
                >
                  Full resolution
                </button>
              ) : null}
            </div>
          </GlassPanel>
        ))}
        {!items.length && data ? (
          <GlassPanel className="sm:col-span-2 lg:col-span-3">
            <p className="text-sm text-fg-muted">
              No downloaded sample timeslots yet. Run discovery → sample → download
              → processing from the dashboard first.
            </p>
          </GlassPanel>
        ) : null}
      </div>

      {lightbox?.image_url ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Final Globe Mix full resolution"
          onClick={() => setLightbox(null)}
        >
          <div
            className="relative flex max-h-[92vh] w-full max-w-5xl flex-col gap-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-glass-border bg-[#0c141c]/95 px-4 py-3 text-white">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">
                  Final Globe Mix · {lightbox.date} · {displayTime(lightbox.time)}{" "}
                  UTC
                </p>
                <p className="truncate text-xs text-slate-300">
                  {lightbox.sample_role || "sample"} · role-aware hero mix
                </p>
              </div>
              <button
                type="button"
                onClick={() => setLightbox(null)}
                className="rounded-full border border-accent/50 bg-accent/20 px-3 py-1.5 text-xs font-medium text-accent-soft hover:bg-accent/30"
              >
                Close (Esc)
              </button>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={lightbox.image_url}
              alt={`Final Globe Mix ${lightbox.date} ${displayTime(lightbox.time)}`}
              className="mx-auto max-h-[78vh] w-auto max-w-full rounded-xl border border-white/10 object-contain"
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
