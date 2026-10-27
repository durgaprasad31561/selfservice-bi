/** @type {import('tailwindcss').Config} */
// Colors are CSS variables (see src/index.css) so light/dark are swapped in one place.
const v = (name) => `var(--${name})`;
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "Consolas", "monospace"],
      },
      colors: {
        page: v("page"),
        surface: v("surface-1"),
        "surface-2": v("surface-2"),
        ink: v("text-primary"),
        "ink-2": v("text-secondary"),
        muted: v("text-muted"),
        line: v("border"),
        grid: v("grid"),
        accent: v("accent"),
        "accent-ink": v("accent-ink"),
        "accent-soft": v("accent-soft"),
        good: v("status-good"),
        warn: v("status-warning"),
        "warn-soft": v("warn-soft"),
        "warn-ink": v("warn-ink"),
        critical: v("status-critical"),
        "info-soft": v("info-soft"),
      },
    },
  },
  plugins: [],
};
