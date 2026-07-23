import { ReactNode } from "react";
import { GlassPanel } from "./GlassPanel";

type Props = {
  title?: string;
  children: ReactNode;
  className?: string;
};

/**
 * Consistent wrapper for self-explanatory guidance copy (BUILDPLAN §14 / §15).
 */
export function ExplainBlock({ title, children, className = "" }: Props) {
  return (
    <GlassPanel className={className} padding="md">
      {title ? (
        <h2 className="mb-3 text-lg font-semibold tracking-tight text-accent-soft">
          {title}
        </h2>
      ) : null}
      <div className="space-y-3 text-[15px] leading-relaxed text-fg-soft">
        {children}
      </div>
    </GlassPanel>
  );
}
