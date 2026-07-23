"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ExplainBlock } from "@/components/ui/ExplainBlock";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api, DateSummary, Timeslot, formatBytes } from "@/lib/api-client";

function displayTime(hhmm: string | null | undefined): string {
  if (!hhmm) return "—";
  return hhmm.replace(/-/g, ":");
}

export default function BrowsePage() {
  const [dates, setDates] = useState<DateSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [slots, setSlots] = useState<Timeslot[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .dates()
      .then(setDates)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selected) {
      setSlots([]);
      return;
    }
    api
      .timeslots({ date: selected, sampled_only: true })
      .then(setSlots)
      .catch((e) => setError(e.message));
  }, [selected]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-fg-heading">Browse</h1>
        <p className="mt-1 text-fg-muted">
          Date-first navigation across the discovered archive and the 3-role sample
        </p>
      </div>

      <ExplainBlock title="How to read a date row">
        <p>
          Each date shows how many timeslots exist on the server, and how many of
          the three sample roles (daytime / twilight / nighttime) could actually
          be filled. Roles prefer times near the standard targets; if a target has
          no match within tolerance, the nearest remaining file on that date is
          used. Those off-target picks still show their <em>exact archive time</em>{" "}
          so you can see they are valid data, just not at the usual day/twilight/night
          clock time. Empty calendar days with no files do not appear after discovery.
        </p>
      </ExplainBlock>

      {error ? (
        <GlassPanel className="border-rose-400/40">
          <p className="text-sm text-rose-700 theme-dark:text-rose-100">{error}</p>
        </GlassPanel>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <GlassPanel padding="sm" className="max-h-[70vh] overflow-auto">
          <h2 className="mb-3 px-2 text-sm font-semibold uppercase tracking-wider text-fg-subtle">
            Dates ({dates.length})
          </h2>
          <ul className="space-y-1">
            {dates.map((d) => (
              <li key={d.date}>
                <button
                  type="button"
                  onClick={() => setSelected(d.date)}
                  className={[
                    "flex w-full items-start justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition",
                    selected === d.date
                      ? "bg-accent/15 ring-1 ring-accent/30"
                      : "hover:bg-surface-hover",
                  ].join(" ")}
                >
                  <div>
                    <div className="font-medium text-fg-heading">{d.date}</div>
                    <div className="text-xs text-fg-muted">{d.sample_label}</div>
                  </div>
                  <div className="text-right text-xs text-fg-subtle">
                    <div>{d.discovered_count} on server</div>
                    <div>{formatBytes(d.total_bytes)}</div>
                  </div>
                </button>
              </li>
            ))}
            {!dates.length ? (
              <li className="px-3 py-6 text-sm text-fg-muted">
                No dates yet — run discovery from the dashboard.
              </li>
            ) : null}
          </ul>
        </GlassPanel>

        <GlassPanel>
          <h2 className="mb-3 text-lg font-semibold text-fg-heading">
            {selected ? `Sample for ${selected}` : "Select a date"}
          </h2>
          {selected ? (
            <div className="mb-4 flex flex-wrap gap-2">
              <Link
                href={`/compare?date=${encodeURIComponent(selected)}`}
                className="inline-flex rounded-full border border-accent/40 bg-accent/10 px-3 py-1.5 text-sm text-accent-soft hover:bg-accent/20"
              >
                Compare day / twilight / night →
              </Link>
              <Link
                href="/final-globes"
                className="inline-flex rounded-full border border-glass-border px-3 py-1.5 text-sm text-fg-soft hover:bg-surface-hover"
              >
                Final Globes →
              </Link>
            </div>
          ) : null}
          {selected && !slots.length ? (
            <p className="text-sm text-fg-muted">
              No sample roles selected for this date yet. Run sample selection
              from the dashboard, or this date may have no discoverable files.
            </p>
          ) : null}
          <ul className="space-y-3">
            {slots.map((ts) => {
              const offTarget = ts.sample_match === "nearest_fallback";
              return (
                <li key={ts.id}>
                  <Link
                    href={`/timeslot/${ts.id}`}
                    className={[
                      "block rounded-xl border bg-surface-panel p-4 transition hover:border-accent/30 hover:bg-accent/5",
                      offTarget
                        ? "border-amber-400/35"
                        : "border-glass-border",
                    ].join(" ")}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-lg font-medium text-fg-heading">
                        {displayTime(ts.time)}
                      </span>
                      {ts.sample_role ? (
                        <StatusBadge status={ts.sample_role} />
                      ) : null}
                      {offTarget ? (
                        <span className="rounded-md border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-amber-800 theme-dark:text-amber-200">
                          Nearest available
                        </span>
                      ) : null}
                      <StatusBadge
                        status={
                          ts.products_complete
                            ? "processed"
                            : (ts.products_generated ?? 0) === 0 &&
                                ts.download_status === "downloaded"
                              ? "failed"
                              : ts.download_status
                        }
                      />
                    </div>

                    {offTarget ? (
                      <p className="mt-2 text-sm leading-relaxed text-fg-heading">
                        Exact archive time{" "}
                        <span className="font-semibold tabular-nums">
                          {displayTime(ts.time)}
                        </span>
                        {" · "}
                        nearest available for {ts.sample_role}
                        {ts.sample_target_time ? (
                          <>
                            {" "}
                            (standard target{" "}
                            <span className="tabular-nums">
                              {displayTime(ts.sample_target_time)}
                            </span>
                            )
                          </>
                        ) : null}
                      </p>
                    ) : ts.sample_target_time ? (
                      <p className="mt-2 text-xs text-fg-muted">
                        Near standard {ts.sample_role} target{" "}
                        <span className="tabular-nums">
                          {displayTime(ts.sample_target_time)}
                        </span>
                      </p>
                    ) : null}

                    {offTarget ? (
                      <p className="mt-1.5 text-xs leading-relaxed text-fg-muted">
                        Valid data from this date — not at the usual{" "}
                        {ts.sample_role} clock time because no file existed near{" "}
                        <span className="tabular-nums">
                          {displayTime(ts.sample_target_time)}
                        </span>
                        .
                      </p>
                    ) : null}

                    <p className="mt-2 text-xs text-fg-muted">
                      {formatBytes(ts.server_reported_size_bytes || 0)}
                      {ts.products_generated != null
                        ? ` · ${ts.products_generated} products generated`
                        : ""}
                      {ts.last_error ? ` · ${ts.last_error}` : ""}
                    </p>
                  </Link>
                </li>
              );
            })}
          </ul>
        </GlassPanel>
      </div>
    </div>
  );
}
