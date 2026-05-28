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
          muted: "var(--popory-muted)",
          accent: "var(--popory-accent)",
          card: "var(--popory-card)",
          border: "var(--popory-border)",
        },
      },
      typography: {
        popory: {
          css: {
            "--tw-prose-body": "var(--popory-fg)",
            "--tw-prose-headings": "var(--popory-fg)",
            "--tw-prose-links": "var(--popory-accent)",
            "--tw-prose-quotes": "var(--popory-muted)",
            "--tw-prose-bullets": "var(--popory-muted)",
            "--tw-prose-counters": "var(--popory-muted)",
            "--tw-prose-hr": "var(--popory-border)",
            "--tw-prose-th-borders": "var(--popory-border)",
            "--tw-prose-td-borders": "var(--popory-border)",
            "--tw-prose-code": "var(--popory-fg)",
            "--tw-prose-pre-bg": "var(--popory-card)",
          },
        },
      },
    },
  },
  plugins: [typography],
};
export default config;
