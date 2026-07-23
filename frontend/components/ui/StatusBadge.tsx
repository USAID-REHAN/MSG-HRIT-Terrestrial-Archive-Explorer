type Props = {
  status: string;
  kind?: "download" | "availability" | "job" | "role";
};

const STYLES: Record<string, string> = {
  discovered:
    "border-slate-500/40 bg-slate-500/15 text-slate-700 theme-dark:text-slate-200",
  queued:
    "border-sky-500/40 bg-sky-500/15 text-sky-800 theme-dark:text-sky-200",
  downloading: "border-accent/40 bg-accent/15 text-accent-soft",
  downloaded:
    "border-teal-500/40 bg-teal-500/15 text-teal-800 theme-dark:text-teal-100",
  failed:
    "border-rose-400/50 bg-rose-500/15 text-rose-700 theme-dark:text-rose-200",
  processed:
    "border-emerald-500/40 bg-emerald-500/15 text-emerald-800 theme-dark:text-emerald-100",
  generated:
    "border-emerald-500/40 bg-emerald-500/15 text-emerald-800 theme-dark:text-emerald-100",
  unavailable_night:
    "border-amber-500/45 bg-amber-500/12 text-amber-800 theme-dark:text-amber-100",
  unavailable_error:
    "border-rose-400/50 bg-rose-500/15 text-rose-700 theme-dark:text-rose-200",
  running: "border-accent/40 bg-accent/15 text-accent-soft",
  completed:
    "border-emerald-500/40 bg-emerald-500/15 text-emerald-800 theme-dark:text-emerald-100",
  paused:
    "border-amber-500/45 bg-amber-500/12 text-amber-800 theme-dark:text-amber-100",
  daytime:
    "border-amber-400/40 bg-amber-400/10 text-amber-800 theme-dark:text-amber-100",
  nighttime:
    "border-slate-400/35 bg-slate-400/10 text-slate-700 theme-dark:text-slate-100",
  twilight:
    "border-orange-400/40 bg-orange-400/10 text-orange-800 theme-dark:text-orange-100",
};

const LABELS: Record<string, string> = {
  discovered: "Discovered",
  queued: "Queued",
  downloading: "Downloading",
  downloaded: "Downloaded",
  failed: "Failed",
  processed: "Processed",
  generated: "Generated",
  unavailable_night: "Unavailable (night)",
  unavailable_error: "Unavailable (error)",
  running: "Running",
  completed: "Completed",
  paused: "Paused",
  queued_job: "Queued",
  daytime: "Daytime sample",
  nighttime: "Nighttime sample",
  twilight: "Twilight sample",
};

export function StatusBadge({ status }: Props) {
  const style =
    STYLES[status] ||
    "border-fg-muted/30 bg-surface-hover text-fg-soft";
  const label = LABELS[status] || status.replaceAll("_", " ");
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium tracking-wide ${style}`}
      title={label}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" aria-hidden />
      {label}
    </span>
  );
}
