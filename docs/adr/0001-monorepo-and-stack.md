<!-- popory F0 시점의 인프라·언어·monorepo 도구 선택을 기록한다. -->

# ADR 0001 — Monorepo + Cloudflare-first 스택 채택

## 상태
2026-05-27 채택. (spec: 2026-05-27 popory platform foundation)

## 컨텍스트
poporyfamily.com을 5개 영역의 허브로 운영해야 한다. 영역마다 워크로드가 달라 백엔드 언어는 폴리글랏이며, 기존 daily-brief Python 자산을 살린다.

## 결정
- pnpm + Turborepo로 TypeScript 영역(apps·workers·packages)을 묶는다.
- 포털·가벼운 API는 Cloudflare Pages + Workers + D1/R2/KV로 한다.
- 무거운 Python 워크로드는 외부(Fly.io 등)로 둔다.
- 사용자 인증은 Google OAuth + 포털 화이트리스트.

## 결과
- 모든 TS 패키지의 공유 toolchain이 단일화된다.
- 영역별 호스팅이 분리되어 secret·배포 파이프라인이 늘어나지만, 운영 부담은 영역 단위로 격리된다.
