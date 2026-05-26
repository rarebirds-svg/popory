# popory

poporyfamily.com 멀티 서비스 플랫폼의 monorepo. F0(포털 골격) 구현 중.

## 구성
- `apps/portal` — Next.js 포털 (Cloudflare Pages)
- `workers/api` — 포털 API (Hono on Workers)
- `packages/{config,types,auth,ui}` — 공통 패키지
- `infra/{wrangler,migrations}` — Cloudflare 설정과 D1 스키마

## 실행
```
pnpm install
pnpm dev
```

자세한 설계는 내부 spec(`docs/superpowers/specs/2026-05-27-popory-platform-foundation-design.md`)을 참고하세요. spec 파일은 popory monorepo 외부 저장소에 위치합니다.
