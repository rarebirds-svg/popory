// 포털 Tailwind 설정. popory 토큰을 CSS 변수로 받는다.
import type { Config } from "tailwindcss";

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
    },
  },
};
export default config;
