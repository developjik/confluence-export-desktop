/** @type {import('tailwindcss').Config} */
export default {
  content: ["ui/index.html", "ui/src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "hsl(var(--c-bg) / <alpha-value>)",
        surface: "hsl(var(--c-surface) / <alpha-value>)",
        raised: "hsl(var(--c-raised) / <alpha-value>)",
        border: "hsl(var(--c-border) / <alpha-value>)",
        strong: "hsl(var(--c-strong) / <alpha-value>)",
        text: "hsl(var(--c-text) / <alpha-value>)",
        muted: "hsl(var(--c-muted) / <alpha-value>)",
        faint: "hsl(var(--c-faint) / <alpha-value>)",
        accent: "hsl(var(--c-accent) / <alpha-value>)",
        "accent-soft": "hsl(var(--c-accent-soft) / <alpha-value>)",
        ok: "hsl(var(--c-ok) / <alpha-value>)",
        warn: "hsl(var(--c-warn) / <alpha-value>)",
        err: "hsl(var(--c-err) / <alpha-value>)",
      },
      fontFamily: {
        sans: [
          "Pretendard Variable",
          "Pretendard",
          "-apple-system",
          "BlinkMacSystemFont",
          "Apple SD Gothic Neo",
          "Segoe UI",
          "Noto Sans KR",
          "Malgun Gothic",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "JetBrains Mono", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px hsl(var(--c-shadow) / 0.06), 0 4px 16px hsl(var(--c-shadow) / 0.05)",
        pop: "0 8px 32px hsl(var(--c-shadow) / 0.18)",
      },
    },
  },
  plugins: [],
};
