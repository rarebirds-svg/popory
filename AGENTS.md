# popory — AGENTS.md

poporyfamily.com 멀티 서비스 플랫폼 monorepo. 공통 행동 규칙은 상위 `~/projects/AGENTS.md`를 따른다.

## 전역 지침 (모든 세션 공통)

- 사용자에게 보이는 진행 과정 설명·중간 보고·최종 요약은 **반드시 한글**로 쓴다. 코드·식별자·명령어는 원문 그대로 둔다.

## 스택

- pnpm 9 workspace + turbo, Node >= 20.10, TypeScript 5.6
- `apps/portal` — Next.js 포털 (Cloudflare Pages 배포)
- `workers/api` — Hono on Cloudflare Workers API
- `packages/{config,types,auth,ui}` — 공통 패키지
- `infra/{wrangler,migrations}` — Cloudflare 설정, D1 스키마

## 명령

```bash
pnpm install
pnpm dev          # turbo run dev --parallel
pnpm test         # turbo run test
pnpm lint && pnpm typecheck
```

## 주의

- 설계 spec은 이 레포 밖 `~/projects/docs/superpowers/specs/`에 있다 (2026-05-27-popory-platform-foundation-design.md).
- Cloudflare 배포·wrangler 설정 변경은 `infra/wrangler`에서만 한다.
- 브리핑 publish 엔드포인트는 Cloudflare UA가 필요하고 키 미활성 시 401을 반환한다 (2026-06-05 기준, portal 미프로비저닝).
