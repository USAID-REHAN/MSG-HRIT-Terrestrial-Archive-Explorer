import { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  padding?: "sm" | "md" | "lg";
  hover?: boolean;
};

const pad = { sm: "p-4", md: "p-6", lg: "p-8" };

export function GlassPanel({
  children,
  className = "",
  padding = "md",
  hover = false,
}: Props) {
  return (
    <div
      className={[
        "relative rounded-2xl border border-glass-border",
        "bg-surface-glass backdrop-blur-xl",
        "shadow-glass",
        "before:pointer-events-none before:absolute before:inset-0 before:rounded-2xl",
        "before:bg-gradient-to-br before:from-white/[0.07] before:to-transparent before:opacity-80",
        "theme-light:before:from-white/40 theme-light:before:opacity-60",
        pad[padding],
        hover
          ? "transition duration-300 hover:border-accent/35 hover:shadow-[0_8px_40px_rgba(45,212,191,0.12)]"
          : "",
        className,
      ].join(" ")}
    >
      <div className="relative z-[1]">{children}</div>
    </div>
  );
}
