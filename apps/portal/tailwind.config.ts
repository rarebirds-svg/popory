// 포털 Tailwind 설정. popory 토큰을 CSS 변수로 받고, prose-popory 변형을 정의한다.
import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        popory: {
          bg: "var(--popory-bg)",
          fg: "var(--popory-fg)",
          fg2: "var(--popory-fg2)",
          muted: "var(--popory-muted)",
          accent: "var(--popory-accent)",
          "accent-soft": "var(--popory-accent-soft)",
          success: "var(--popory-success)",
          "success-soft": "var(--popory-success-soft)",
          warn: "var(--popory-warn)",
          "warn-soft": "var(--popory-warn-soft)",
          danger: "var(--popory-danger)",
          "danger-soft": "var(--popory-danger-soft)",
          card: "var(--popory-card)",
          border: "var(--popory-border)",
        },
      },
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "var(--font-sans-kr)", "system-ui", "sans-serif"],
      },
      typography: {
        popory: {
          css: {
            "--tw-prose-body": "var(--popory-fg2)",
            "--tw-prose-headings": "var(--popory-fg)",
            "--tw-prose-links": "var(--popory-accent)",
            "--tw-prose-bold": "var(--popory-fg)",
            "--tw-prose-quotes": "var(--popory-fg2)",
            "--tw-prose-quote-borders": "var(--popory-accent)",
            "--tw-prose-bullets": "var(--popory-muted)",
            "--tw-prose-counters": "var(--popory-muted)",
            "--tw-prose-hr": "var(--popory-border)",
            "--tw-prose-th-borders": "var(--popory-border)",
            "--tw-prose-td-borders": "var(--popory-border)",
            "--tw-prose-code": "var(--popory-fg)",
            "--tw-prose-pre-bg": "var(--popory-card)",
            maxWidth: "42rem",
            fontSize: "1.0625rem",
            lineHeight: "1.8",
            h1: { fontFamily: "var(--font-serif)", letterSpacing: "-0.02em" },
            h2: { fontFamily: "var(--font-serif)", letterSpacing: "-0.01em" },
            h3: { fontFamily: "var(--font-serif)" },
          },
        },
      },
    },
  },
  plugins: [typography],
};
export default config;
