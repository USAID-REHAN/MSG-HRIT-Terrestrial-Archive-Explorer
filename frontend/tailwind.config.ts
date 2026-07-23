import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#070b10",
          900: "#0c1219",
          800: "#121a24",
          700: "#1a2433",
        },
        glass: {
          border: "var(--glass-border)",
          highlight: "rgba(120, 220, 210, 0.12)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          soft: "var(--accent-soft)",
          deep: "var(--accent-deep)",
          amber: "var(--accent-amber)",
        },
        fg: {
          DEFAULT: "var(--text)",
          heading: "var(--text-heading)",
          soft: "var(--text-soft)",
          muted: "var(--text-muted)",
          subtle: "var(--text-subtle)",
        },
        surface: {
          DEFAULT: "var(--bg-deep)",
          panel: "var(--surface-panel)",
          hover: "var(--surface-hover)",
          nav: "var(--bg-nav)",
          glass: "var(--glass-bg)",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-geist-sans)",
          "Segoe UI",
          "system-ui",
          "sans-serif",
        ],
        display: [
          "var(--font-geist-sans)",
          "Segoe UI",
          "system-ui",
          "sans-serif",
        ],
      },
      boxShadow: {
        glass: "var(--shadow-glass)",
        "glass-sm":
          "0 4px 16px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.06)",
      },
      backgroundImage: {
        atmosphere: "var(--atmosphere)",
      },
    },
  },
  plugins: [
    plugin(({ addVariant }) => {
      addVariant("theme-dark", '[data-theme="dark"] &');
      addVariant("theme-light", '[data-theme="light"] &');
    }),
  ],
};

export default config;
