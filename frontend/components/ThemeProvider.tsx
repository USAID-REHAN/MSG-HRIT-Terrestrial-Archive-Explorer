"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Theme = "dark" | "light";

type ThemeContextValue = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = "hrit-theme";
const TRANSITION_MS = 320;

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

/**
 * CSS-only theme fade. Avoid document.startViewTransition — Next.js / React
 * navigations and dashboard polling often abort it with
 * `AbortError: Transition was skipped`, which Next surfaces as an unhandled
 * runtime error overlay.
 */
function runThemeChange(theme: Theme) {
  const root = document.documentElement;
  root.classList.add("theme-transitioning");
  applyTheme(theme);
  window.setTimeout(() => {
    root.classList.remove("theme-transitioning");
  }, TRANSITION_MS);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    const current = document.documentElement.dataset.theme;
    const next = current === "light" || current === "dark" ? current : "dark";
    applyTheme(next);
    setThemeState(next);
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState((prev) => {
      if (prev === next) return prev;
      runThemeChange(next);
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* ignore quota / private mode */
      }
      return next;
    });
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      runThemeChange(next);
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* ignore quota / private mode */
      }
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme]
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return ctx;
}
