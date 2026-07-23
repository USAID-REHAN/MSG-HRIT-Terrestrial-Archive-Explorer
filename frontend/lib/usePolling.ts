"use client";

import { useEffect, useRef } from "react";

/**
 * Interval that skips ticks while the pointer is down or the tab is hidden.
 * Prevents poll-driven React re-renders from replacing DOM nodes between
 * mousedown and click (the classic “needs a second click” failure).
 */
export function usePolling(
  fn: () => void | Promise<void>,
  intervalMs: number,
  enabled = true,
) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!enabled) return;

    let pointerDown = false;
    const onDown = () => {
      pointerDown = true;
    };
    const onUp = () => {
      pointerDown = false;
    };

    window.addEventListener("pointerdown", onDown, true);
    window.addEventListener("pointerup", onUp, true);
    window.addEventListener("pointercancel", onUp, true);

    const tick = () => {
      if (pointerDown) return;
      if (document.visibilityState === "hidden") return;
      void fnRef.current();
    };

    void tick();
    const id = window.setInterval(tick, intervalMs);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("pointerup", onUp, true);
      window.removeEventListener("pointercancel", onUp, true);
    };
  }, [intervalMs, enabled]);
}
