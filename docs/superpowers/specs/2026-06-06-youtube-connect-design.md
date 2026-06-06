<!-- Slice 2-A: 가족 구성원이 자신의 YouTube 채널을 OAuth로 연결하고 refresh token을 암호화 저장하는 디자인 spec. -->
---
title: popory — YouTube 채널 연결 (Slice 2-A)
date: 2026-06-06
status: draft
related:
  - docs/superpowers/specs/2026-06-06-youtube-video-generation-design.md
---

# YouTube 채널 연결 design (Slice 2-A)

## 1. 동기

YouTube 자동 업로드(Slice 2)의 전제 — 각 가족 구성원이 **자신의 YouTube 채널**을 popory에 연결해야 한다. 본 슬라이스는 연결(OAuth 인가 + refresh token 암호화 저장 + 연결 상태 표시)까지만 다룬다. 실제 업로드는 후속(Slice 2-B).

기존 로그인 Google OAuth(`/auth/google/*`)와 별개 흐름 — 스코프(`youtube.upload`)·redirect URI 가 다르고, 이미 로그인한 사용자가 추가 인가를 하는 것이다.

## 2. 비목표 (Slice 2-A 제외)

- **업로드 없음** (Slice 2-B).
- **단일 가족 채널 아님** — 멤버별 연결.
- **앱 검증 처리 없음** — 미검증 앱이라 업로드 영상은 후속에서 비공개로 올라갈 수 있음(연결 단계 무관).

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| 인가 흐름 | Authorization Code + `access_type=offline` + `prompt=consent`(refresh token 강제) |
| 스코프 | `youtube.upload` + `youtube.readonly`(채널명 조회용) |
| OAuth client | 기존 `GOOGLE_CLIENT_ID/SECRET` 재사용 |
| redirect URI | `${PUBLIC_BASE_URL}/api/content/youtube/callback` |
| state(CSRF) | KV `oauth:youtube:state:{state}` → `{sub}` (연결 시작한 사용자) |
| 토큰 저장 | D1 `youtube_connections`, refresh token 은 AES-GCM 암호화(`YOUTUBE_TOKEN_KEY` secret) |
| 연결 UI | 포털 `/content/youtube` — 상태 + 연결/해제 |

## 4. 아키텍처

```
[포털 /content/youtube] "YouTube 연결"
  → GET /api/content/youtube/connect (쿠키 인증)
      state{sub} KV 저장 → 302 accounts.google.com (scope youtube.upload, offline, consent)
  ← Google 동의 후 GET /api/content/youtube/callback?code&state
      state 검증 → 토큰 교환(refresh_token+access_token)
      → youtube.channels.list(mine) 로 채널명 → refresh_token 암호화 → D1 upsert
      → 302 ${PORTAL_ORIGIN}/content/youtube?connected=1
[포털] GET /api/content/youtube/status → {connected, channel_title}
```

## 5. 컴포넌트별

### 5.1 D1 (`infra/migrations/0004_youtube.sql`)
```sql
CREATE TABLE youtube_connections (
  sub             TEXT PRIMARY KEY REFERENCES users(sub) ON DELETE CASCADE,
  channel_id      TEXT,
  channel_title   TEXT,
  refresh_token   TEXT NOT NULL,   -- AES-GCM 암호문(base64)
  connected_at    INTEGER NOT NULL
);
```

### 5.2 암호화 (`workers/api/src/lib/secretbox.ts` 신규)
- `encrypt(plaintext, keyB64) -> string`(base64 iv+ct), `decrypt(token, keyB64) -> string`. Web Crypto AES-GCM, 256bit 키.
- `YOUTUBE_TOKEN_KEY` 는 base64(32 bytes) Worker secret.

### 5.3 라우트 (`workers/api/src/routes/content_youtube.ts` 신규)
- `GET /api/content/youtube/connect` — `requireAuth`. `state=uuid` → KV `oauth:youtube:state:{state}={sub}`(TTL 600) → Google 인가 URL 302(client_id, redirect_uri, scope, access_type=offline, prompt=consent, state, response_type=code).
- `GET /api/content/youtube/callback` — `code`·`state` 쿼리. KV 에서 state→sub 조회(없으면 400), KV 삭제. 토큰 교환(POST oauth2 token, grant_type=authorization_code) → `{refresh_token, access_token}`. refresh_token 없으면(재동의 아님) 에러 안내 리다이렉트. `GET youtube/v3/channels?part=snippet&mine=true`(access_token) → channel id/title. refresh_token 암호화 → `INSERT OR REPLACE youtube_connections`. 302 `${PORTAL_ORIGIN}/content/youtube?connected=1`.
- `GET /api/content/youtube/status` — `requireAuth` → `{connected: bool, channel_title: string|null}`(refresh_token 노출 안 함).
- `DELETE /api/content/youtube/connect` — `requireAuth` → 행 삭제 → 204.
- `app.ts` mount.

### 5.4 포털 (`apps/portal/src/app/(authed)/content/youtube/page.tsx` 신규)
- 서버에서 status fetch → 연결됨이면 채널명 + "연결 해제"(client), 아니면 "YouTube 연결" 링크(`${API_BASE}/api/content/youtube/connect`).
- 콘텐츠 목록(`/content`)에 "YouTube 연결" 링크 추가.

### 5.5 설정 (운영자/사용자)
- Google Cloud `popory-497615`: YouTube Data API v3 활성화. OAuth 동의화면에 `youtube.upload`·`youtube.readonly` 스코프 추가. redirect URI `https://api.poporyfamily.com/api/content/youtube/callback` 등록.
- Worker secret `YOUTUBE_TOKEN_KEY`(base64 32 bytes) 주입.

## 6. 에러 처리

- state 없음/만료 → 400(또는 에러 리다이렉트).
- refresh_token 미수신(이미 동의해 prompt 생략된 경우) → `prompt=consent` 로 강제하므로 보통 수신. 그래도 없으면 사용자에게 "다시 연결" 안내 리다이렉트.
- 토큰 교환/채널 조회 실패 → 에러 리다이렉트(`?error=...`).

## 7. 테스트

- `secretbox.ts` vitest — encrypt→decrypt 라운드트립, 잘못된 키 실패.
- 라우트 vitest — connect 가 302 + accounts.google.com 로 가는지·state KV 저장, status(연결/미연결), 미인증 401, disconnect 204. (실제 Google 토큰 교환·callback 완주는 외부라 e2e.)
- 포털 — typecheck + build.

## 8. 미해결·후속

- 실제 callback(Google 토큰 교환) 동작은 외부 설정 완료 후 e2e.
- Slice 2-B: 업로드 버튼 + 워커 업로드 작업.
- 토큰 키 회전·다채널(한 사용자 여러 채널)은 후속.
