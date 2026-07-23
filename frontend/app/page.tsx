"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ExplainBlock } from "@/components/ui/ExplainBlock";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api, DashboardStats, formatBytes } from "@/lib/api-client";
import { usePolling } from "@/lib/usePolling";

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <GlassPanel padding="sm" className="min-w-0">
      <div className="text-[11px] uppercase tracking-[0.16em] text-fg-subtle">
        {label}
      </div>
      <div className="mt-1 truncate text-2xl font-semibold text-fg-heading">{value}</div>
      {hint ? <div className="mt-1 text-xs text-fg-muted">{hint}</div> : null}
    </GlassPanel>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const diskRequested = useRef(false);
  const pendingAction = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const d = await api.dashboard();
      setStats((prev) => {
        // Dashboard no longer walks disk — keep a previously loaded breakdown.
        if (d.disk_breakdown || !prev?.disk_breakdown) return d;
        return {
          ...d,
          disk_breakdown: prev.disk_breakdown,
          disk_used_data_gb: prev.disk_used_data_gb,
          downloaded_bytes_on_disk:
            prev.disk_breakdown.raw_bytes || d.downloaded_bytes_on_disk,
          disk_free_gb: prev.disk_breakdown.free_gb || d.disk_free_gb,
        };
      });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(refresh, 5000);

  // Disk walk is heavy — load it AFTER first stats paint, once, never on the critical path.
  useEffect(() => {
    if (!stats || stats.disk_breakdown || diskRequested.current) return;
    diskRequested.current = true;
    let cancelled = false;

    const applyDisk = (disk: {
      raw_bytes: number;
      processed_bytes: number;
      thumbnails_bytes: number;
      catalog_bytes: number;
      total_bytes: number;
      free_gb: number;
    }) => {
      if (cancelled || disk.total_bytes <= 0) return false;
      setStats((prev) =>
        prev
          ? {
              ...prev,
              disk_breakdown: disk,
              disk_used_data_gb: Number((disk.total_bytes / 1024 ** 3).toFixed(2)),
              downloaded_bytes_on_disk: disk.raw_bytes,
              disk_free_gb: disk.free_gb,
            }
          : prev
      );
      return true;
    };

    const t = setTimeout(async () => {
      try {
        await api.diskUsage(true); // kick background walk
        for (let i = 0; i < 8 && !cancelled; i++) {
          await new Promise((r) => setTimeout(r, 1500));
          const disk = await api.diskUsage(false);
          if (applyDisk(disk)) break;
        }
      } catch {
        /* disk is optional */
      }
    }, 1200);

    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [stats]);

  async function run(label: string, fn: () => Promise<{ ok: boolean; error?: string | null }>) {
    if (pendingAction.current) return;
    pendingAction.current = true;
    setBusy(label);
    setError(null);
    setNotice(null);
    const started = Date.now();
    try {
      const r = await fn();
      if (!r.ok) {
        setError(r.error || `${label} failed`);
      } else {
        setNotice(`${label} started`);
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : `${label} failed`);
    } finally {
      const elapsed = Date.now() - started;
      if (elapsed < 300) {
        await new Promise((resolve) => window.setTimeout(resolve, 300 - elapsed));
      }
      setBusy(null);
      pendingAction.current = false;
    }
  }

  const cfg = stats?.config_snapshot || {};

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-fg-heading">
          Dashboard
        </h1>
        <p className="mt-1 text-fg-muted">
          Catalog the full archive · download a daylight/night/twilight sample ·
          process SEVIRI products locally
        </p>
      </div>

      <ExplainBlock title="What this tool does">
        <p>
          <strong className="text-fg-heading">MSG</strong> (Meteosat Second
          Generation) carries the{" "}
          <strong className="text-fg-heading">SEVIRI</strong> imager, which observes
          Earth in twelve spectral channels from geostationary orbit. This
          archive holds whole-disk scans as single{" "}
          <code className="text-accent-soft">msg15.nat</code> Native-format
          files on the SATMET internal server.
        </p>
        <p>
          The explorer <em>catalogs every timeslot</em> it finds, but by default
          only <strong className="text-fg-heading">downloads three per date</strong>
          — a daytime, twilight, and nighttime scan. Those three cover every
          processing behaviour that matters (solar channels present, partial
          terminator, solar channels unavailable at night). The full archive
          can exceed ~275 GB; the sample stays around 15 GB so you can iterate
          quickly for review and demos.
        </p>
        <p>
          Processed images support four practical sectors:{" "}
          <strong className="text-fg-heading">agriculture</strong>,{" "}
          <strong className="text-fg-heading">aviation</strong>,{" "}
          <strong className="text-fg-heading">natural resource monitoring</strong>,
          and <strong className="text-fg-heading">disaster response</strong>. Open{" "}
          <em>About the data</em> for a glossary of every channel and composite.
        </p>
      </ExplainBlock>

      {error ? (
        <GlassPanel className="border-rose-400/40 bg-rose-500/10">
          <p className="text-sm text-rose-700 theme-dark:text-rose-100">{error}</p>
        </GlassPanel>
      ) : null}

      {notice ? (
        <GlassPanel className="border-accent/40 bg-accent/10">
          <p className="text-sm text-accent-soft">{notice}</p>
        </GlassPanel>
      ) : null}

      {loading && !stats ? (
        <GlassPanel>
          <p className="text-sm text-fg-muted">Loading dashboard stats…</p>
        </GlassPanel>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Full archive (discovered)"
          value={String(stats?.discovered_total ?? "—")}
          hint={
            stats
              ? `${formatBytes(stats.discovered_bytes)} on server · ${stats.date_min || "?"} → ${stats.date_max || "?"}`
              : loading
                ? "Loading…"
                : "Run discovery first"
          }
        />
        <Stat
          label="Sample selected"
          value={String(stats?.selected_total ?? "—")}
          hint={
            stats ? `${formatBytes(stats.selected_bytes)} to download` : undefined
          }
        />
        <Stat
          label="Downloaded"
          value={String(stats?.downloaded_total ?? "—")}
          hint={
            stats
              ? `${stats.failed_downloads} failed · ${formatBytes(stats.downloaded_bytes_on_disk)} on disk`
              : undefined
          }
        />
        <Stat
          label="Fully processed"
          value={String(stats?.processed_timeslots ?? "—")}
          hint={
            stats
              ? stats.disk_breakdown
                ? `Data folder ${stats.disk_used_data_gb} GB · free ${stats.disk_free_gb} GB`
                : `Free ${stats.disk_free_gb} GB`
              : undefined
          }
        />
      </div>

      <GlassPanel>
        <h2 className="mb-4 text-lg font-semibold text-accent-soft">
          Pipeline actions
        </h2>
        <div className="mb-3 flex flex-wrap gap-2">
          <ActionButton
            label="Run full pipeline"
            busy={busy === "pipeline"}
            onClick={() => run("pipeline", api.startPipeline)}
          />
          <ActionButton
            label="Pause pipeline"
            variant="ghost"
            onClick={() => run("pause-pipe", api.pausePipeline)}
          />
        </div>
        <p className="mb-4 text-xs text-fg-muted">
          One click runs discovery → sample selection → download → processing in
          order. Individual step buttons below still work if you need to run a
          single stage.
        </p>
        <div className="flex flex-wrap gap-2">
          <ActionButton
            label="Run discovery"
            busy={busy === "discovery"}
            onClick={() => run("discovery", api.runDiscovery)}
          />
          <ActionButton
            label="Run sample selection"
            busy={busy === "sampling"}
            onClick={() => run("sampling", api.runSampling)}
          />
          <ActionButton
            label="Start download"
            busy={busy === "download"}
            onClick={() => run("download", api.startDownload)}
          />
          <ActionButton
            label="Pause download"
            variant="ghost"
            onClick={() => run("pause-dl", api.pauseDownload)}
          />
          <ActionButton
            label="Start processing"
            busy={busy === "processing"}
            onClick={() => run("processing", api.startProcessing)}
          />
          <ActionButton
            label="Pause processing"
            variant="ghost"
            onClick={() => run("pause-px", api.pauseProcessing)}
          />
        </div>
        <p className="mt-4 text-sm text-fg-muted">
          Discovery never downloads <code className="text-accent-soft">.nat</code>{" "}
          files — it only reads directory listings. Sample selection marks which
          discovered timeslots enter the download queue.
        </p>
      </GlassPanel>

      {stats?.disk_breakdown ? (
        <GlassPanel>
          <h2 className="mb-3 text-lg font-semibold text-fg-heading">
            Disk usage breakdown
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Raw (.nat)"
              value={formatBytes(stats.disk_breakdown.raw_bytes)}
            />
            <Stat
              label="Processed PNGs"
              value={formatBytes(stats.disk_breakdown.processed_bytes)}
            />
            <Stat
              label="Thumbnails"
              value={formatBytes(stats.disk_breakdown.thumbnails_bytes)}
            />
            <Stat
              label="Catalog DB"
              value={formatBytes(stats.disk_breakdown.catalog_bytes)}
              hint={`Free ${stats.disk_breakdown.free_gb} GB`}
            />
          </div>
          <p className="mt-3 text-xs text-fg-subtle">
            Total under data/: {formatBytes(stats.disk_breakdown.total_bytes)} ·
            free space on the data volume: {stats.disk_breakdown.free_gb} GB
          </p>
        </GlassPanel>
      ) : stats ? (
        <GlassPanel>
          <h2 className="mb-2 text-lg font-semibold text-fg-heading">
            Disk usage breakdown
          </h2>
          <p className="text-sm text-fg-muted">
            Measuring data folder sizes in the background… stats above are ready.
          </p>
        </GlassPanel>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <GlassPanel>
          <h2 className="mb-3 text-lg font-semibold text-fg-heading">Active / recent jobs</h2>
          {stats?.active_jobs?.length ? (
            <ul className="space-y-3">
              {stats.active_jobs.map((j) => (
                <li
                  key={j.id}
                  className="flex flex-col gap-1 border-b border-glass-border pb-3 last:border-0"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium capitalize text-fg-heading">
                      {j.job_type}
                    </span>
                    <StatusBadge status={j.status} />
                    <span className="text-xs text-fg-subtle">
                      {j.progress_current}/{j.progress_total}
                    </span>
                  </div>
                  <p className="text-sm text-fg-soft">{j.log_summary}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-fg-muted">No active jobs yet.</p>
          )}
        </GlassPanel>

        <GlassPanel>
          <h2 className="mb-3 text-lg font-semibold text-fg-heading">
            Active sample configuration
          </h2>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <ConfigRow label="Daytime target" value={String(cfg.sample_daytime_target ?? "—")} />
            <ConfigRow label="Twilight target" value={String(cfg.sample_twilight_target ?? "—")} />
            <ConfigRow label="Nighttime target" value={String(cfg.sample_nighttime_target ?? "—")} />
            <ConfigRow
              label="Tolerance"
              value={`${cfg.sample_tolerance_minutes ?? "—"} min`}
            />
            <ConfigRow
              label="Files / date"
              value={String(cfg.sample_files_per_date ?? "—")}
            />
            <ConfigRow
              label="Download everything"
              value={String(cfg.download_everything_per_date ?? false)}
            />
            <ConfigRow
              label="Max concurrent DL"
              value={String(cfg.max_concurrent_downloads ?? "—")}
            />
            <ConfigRow
              label="Min free disk"
              value={`${cfg.min_free_disk_gb ?? "—"} GB`}
            />
          </dl>
          <p className="mt-3 text-xs text-fg-subtle">
            Edit via project <code>.env</code> / backend config — not from this UI.
          </p>
        </GlassPanel>
      </div>
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-fg-subtle">{label}</dt>
      <dd className="font-medium text-fg">{value}</dd>
    </>
  );
}

function ActionButton({
  label,
  onClick,
  busy,
  variant = "primary",
}: {
  label: string;
  onClick: () => void;
  busy?: boolean;
  variant?: "primary" | "ghost";
}) {
  // Idle = outline (not filled). Solid teal only while that action is in flight,
  // so primary buttons don't look permanently "selected".
  const idle =
    "border border-glass-border bg-surface-hover text-fg hover:border-accent/40 hover:bg-accent/10 hover:text-accent-soft";
  const active =
    "border border-accent/60 bg-accent text-ink-950 shadow-[0_0_0_1px_rgba(45,212,191,0.35)]";
  const ghostIdle =
    "border border-glass-border/70 bg-transparent text-fg-soft hover:bg-surface-hover hover:text-fg";

  return (
    <button
      type="button"
      disabled={!!busy}
      onClick={onClick}
      aria-pressed={!!busy}
      className={[
        "rounded-full px-4 py-2 text-sm font-medium transition disabled:cursor-wait",
        busy ? active : variant === "ghost" ? ghostIdle : idle,
      ].join(" ")}
    >
      {busy ? `${label}…` : label}
    </button>
  );
}
