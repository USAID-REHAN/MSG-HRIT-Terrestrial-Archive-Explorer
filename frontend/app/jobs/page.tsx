"use client";

import { useCallback, useState } from "react";
import { ExplainBlock } from "@/components/ui/ExplainBlock";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api, Job, Timeslot } from "@/lib/api-client";
import { usePolling } from "@/lib/usePolling";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [failed, setFailed] = useState<Timeslot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [j, fails] = await Promise.all([
        api.jobs(),
        api.timeslots({ download_status: "failed", sampled_only: true, limit: 100 }),
      ]);
      setJobs(j);
      setFailed(fails);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load jobs");
    }
  }, []);

  usePolling(refresh, 3000);

  async function retryDl(id: number) {
    const r = await api.retryDownload(id);
    setMsg(r.ok ? `Retry download queued (#${id})` : r.error || "Retry failed");
    refresh();
  }

  async function retryPx(id: number) {
    const r = await api.retryProcessing(id);
    setMsg(r.ok ? `Retry processing queued (#${id})` : r.error || "Retry failed");
    refresh();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-fg-heading">
          Jobs & status
        </h1>
        <p className="mt-1 text-fg-muted">
          Live progress for discovery, sampling, download, and processing
        </p>
      </div>

      <ExplainBlock title="Resumability">
        <p>
          Every long-running step stores progress in SQLite. If you pause, crash,
          or restart <code className="text-accent-soft">npm run dev</code>, workers
          pick up from database state — completed downloads are never
          re-fetched. Individual timeslot failures do not stop the rest of the
          queue; retry them from the list below.
        </p>
      </ExplainBlock>

      {error ? (
        <GlassPanel className="border-rose-400/40">
          <p className="text-sm text-rose-700 theme-dark:text-rose-100">{error}</p>
        </GlassPanel>
      ) : null}
      {msg ? (
        <GlassPanel>
          <p className="text-sm text-accent-soft">{msg}</p>
        </GlassPanel>
      ) : null}

      <GlassPanel>
        <h2 className="mb-4 text-lg font-semibold text-fg-heading">Job history</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-fg-subtle">
              <tr>
                <th className="pb-2 pr-3">ID</th>
                <th className="pb-2 pr-3">Type</th>
                <th className="pb-2 pr-3">Status</th>
                <th className="pb-2 pr-3">Progress</th>
                <th className="pb-2">Summary</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-t border-glass-border align-top">
                  <td className="py-3 pr-3 text-fg-subtle">#{j.id}</td>
                  <td className="py-3 pr-3 capitalize text-fg-heading">{j.job_type}</td>
                  <td className="py-3 pr-3">
                    <StatusBadge status={j.status} />
                  </td>
                  <td className="py-3 pr-3 text-fg-soft">
                    {j.progress_current}/{j.progress_total}
                    {j.progress_total > 0 ? (
                      <div className="mt-1 h-1.5 w-28 overflow-hidden rounded-full bg-white/10">
                        <div
                          className="h-full rounded-full bg-accent/80"
                          style={{
                            width: `${Math.min(
                              100,
                              (100 * j.progress_current) /
                                Math.max(1, j.progress_total)
                            )}%`,
                          }}
                        />
                      </div>
                    ) : null}
                  </td>
                  <td className="py-3 text-fg-soft">{j.log_summary}</td>
                </tr>
              ))}
              {!jobs.length ? (
                <tr>
                  <td colSpan={5} className="py-6 text-fg-muted">
                    No jobs yet — start one from the dashboard.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </GlassPanel>

      <GlassPanel>
        <h2 className="mb-4 text-lg font-semibold text-fg-heading">
          Failed downloads (retryable)
        </h2>
        <ul className="space-y-3">
          {failed.map((ts) => (
            <li
              key={ts.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-glass-border bg-surface-panel p-3"
            >
              <div>
                <div className="font-medium text-fg-heading">
                  {ts.date} {ts.time}{" "}
                  {ts.sample_role ? (
                    <span className="text-sm text-fg-muted">
                      ({ts.sample_role})
                    </span>
                  ) : null}
                </div>
                <p className="text-xs text-rose-700/90 theme-dark:text-rose-200/90">{ts.last_error}</p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => retryDl(ts.id)}
                  className="rounded-full bg-accent/90 px-3 py-1.5 text-xs font-medium text-ink-950"
                >
                  Retry download
                </button>
                <button
                  type="button"
                  onClick={() => retryPx(ts.id)}
                  className="rounded-full border border-glass-border px-3 py-1.5 text-xs text-fg-soft"
                >
                  Retry processing
                </button>
              </div>
            </li>
          ))}
          {!failed.length ? (
            <li className="text-sm text-fg-muted">No failed downloads.</li>
          ) : null}
        </ul>
      </GlassPanel>
    </div>
  );
}
