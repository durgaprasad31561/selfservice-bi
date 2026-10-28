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
        "line-strong": v("border-strong"),
        grid: v("grid"),
        accent: v("accent"),
        "accent-2": v("accent-2"),
        "accent-ink": v("accent-ink"),
        "accent-soft": v("accent-soft"),
        "accent-text": v("accent-text"),
        sidebar: v("sidebar"),
        "sidebar-2": v("sidebar-2"),
        "sidebar-ink": v("sidebar-ink"),
        "sidebar-muted": v("sidebar-muted"),
        good: v("status-good"),
        "good-soft": v("good-soft"),
        "good-ink": v("good-ink"),
        warn: v("status-warning"),
        "warn-soft": v("warn-soft"),
        "warn-ink": v("warn-ink"),
        critical: v("status-critical"),
        "critical-soft": v("critical-soft"),
        "info-soft": v("info-soft"),
      },
      boxShadow: {
        card: v("shadow-card"),
        lift: v("shadow-lift"),
        glow: v("shadow-glow"),
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.25rem",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out both",
      },
    },
  },
  plugins: [],
};
