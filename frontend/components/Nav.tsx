"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";
import { useTheme } from "@/components/ThemeProvider";
import { api, ConnectivityStatus } from "@/lib/api-client";
import { usePolling } from "@/lib/usePolling";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/browse", label: "Browse" },
  { href: "/globe", label: "Globe" },
  { href: "/final-globes", label: "Final Globes" },
  { href: "/compare", label: "Compare" },
  { href: "/reference", label: "About the data" },
  { href: "/jobs", label: "Jobs" },
];

export function Nav() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();
  const [conn, setConn] = useState<ConnectivityStatus | null>(null);

  const refreshConn = useCallback(async () => {
    try {
      const c = await api.connectivity();
      setConn(c);
    } catch {
      setConn({
        reachable: false,
        archive_url: "",
        latency_ms: null,
        checked_at: new Date().toISOString(),
        error: "Backend unreachable",
        http_status: null,
      });
    }
  }, []);

  usePolling(refreshConn, 30000);

  const badgeTitle = conn
    ? conn.reachable
      ? `Archive reachable${conn.latency_ms != null ? ` · ${conn.latency_ms} ms` : ""}`
      : `Archive unreachable${conn.error ? ` · ${conn.error}` : ""}`
    : "Checking archive…";

  return (
    <header className="sticky top-0 z-40 border-b border-glass-border bg-surface-nav backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="group flex flex-col">
          <span className="text-[11px] uppercase tracking-[0.22em] text-accent/80">
            SATMET · Assignment 04
          </span>
          <span className="text-base font-semibold tracking-tight text-fg-heading transition group-hover:text-accent-soft">
            MSG HRIT Archive Explorer
          </span>
        </Link>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={refreshConn}
            title={badgeTitle}
            aria-label={badgeTitle}
            className={[
              "hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium sm:inline-flex",
              conn?.reachable
                ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-800 theme-dark:text-emerald-200"
                : conn
                  ? "border-rose-400/40 bg-rose-400/10 text-rose-800 theme-dark:text-rose-200"
                  : "border-glass-border text-fg-subtle",
            ].join(" ")}
          >
            <span
              className={[
                "h-1.5 w-1.5 rounded-full",
                conn?.reachable
                  ? "bg-emerald-500"
                  : conn
                    ? "bg-rose-500"
                    : "bg-fg-subtle animate-pulse",
              ].join(" ")}
            />
            {conn?.reachable
              ? "Archive online"
              : conn
                ? "Archive offline"
                : "Checking…"}
          </button>
          <nav className="flex flex-wrap gap-1">
            {LINKS.map((l) => {
              const active =
                l.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(l.href);
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  prefetch
                  className={[
                    "rounded-full px-3 py-1.5 text-sm transition",
                    active
                      ? "bg-accent/20 text-accent-soft"
                      : "text-fg-muted hover:bg-surface-hover hover:text-fg-heading",
                  ].join(" ")}
                >
                  {l.label}
                </Link>
              );
            })}
          </nav>
          <button
            type="button"
            onClick={toggleTheme}
            className="rounded-full border border-glass-border px-3 py-1.5 text-sm text-fg-soft transition-[color,background-color,border-color,box-shadow] duration-300 hover:border-accent/40 hover:bg-accent/10 hover:text-accent-soft"
            aria-label={
              theme === "dark" ? "Switch to light mode" : "Switch to dark mode"
            }
            title={theme === "dark" ? "Light mode" : "Dark mode"}
          >
            {theme === "dark" ? "Light" : "Dark"}
          </button>
        </div>
      </div>
    </header>
  );
}
