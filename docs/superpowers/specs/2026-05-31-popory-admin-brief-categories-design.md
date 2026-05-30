<!-- popory portal admin에서 services/brief 카테고리 SKILL.md를 GitHub Contents API로 read·edit하는 디자인 spec. -->
---
title: popory — portal admin에서 brief 카테고리 SKILL.md 관리 (GitHub source)
date: 2026-05-31
status: draft
related:
  - docs/superpowers/specs/2026-05-30-popory-f1-brief-multi-category-design.md
---

# portal admin · brief 카테고리 SKILL.md 관리 design

## 1. 동기

`services/brief/categories/{slug}/SKILL.md` 본문(system prompt) + frontmatter (slug·name·delivery_mode·subject_template·sender_name·enabled) 6필드를 portal `/admin`에서 열람·수정하려 한다. 현재 편집은 git CLI 또는 IDE 직접만 가능. 비기술자도 활성화 토글이나 prompt 문구 수정을 할 수 있어야 운영이 부드러워진다.

## 2. 비목표

- **카테고리 추가/삭제 UI 없음.** 신규 카테고리는 git에서 `services/brief/categories/{new_slug}/SKILL.md` 추가로 등록 — 본 spec 범위 밖. 추후 amendment에서 다룸.
- **권한 세분화 없음.** `role=admin`이면 모든 카테고리 편집 가능. 카테고리별 편집자 분리 없음.
- **마크다운 라이브 미리보기 없음.** textarea 단순 편집만. monaco/codemirror 도입 없음 (YAGNI).
- **편집 이력 별도 표 없음.** GitHub commit history가 그 역할. 필요하면 admin에 GitHub commits 링크만 노출.

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| 데이터 single source | GitHub `rarebirds-svg/popory` repo의 `services/brief/categories/{slug}/SKILL.md` |
| portal admin → GitHub | Cloudflare Worker 라우트가 GitHub Contents API REST 호출 |
| portal admin UI | 구조화 폼 (frontmatter 6필드 input + system prompt textarea) |
| launchd 적용 | `run_daily.sh` 첫 단계에 `git -C ... pull --ff-only origin main` 1줄 추가 |
| 인증 | 기존 portal admin 권한 (`role=admin`) 그대로 |
| 동시 편집 충돌 | GitHub Contents API의 `sha` 기반 optimistic locking |
| PAT scope | `contents:write` (Fine-grained PAT, 단일 repo `rarebirds-svg/popory`) |
| PAT 보관 | Cloudflare Pages secret `BRIEF_CATEGORIES_GITHUB_TOKEN` |
| commit author | `popory-portal-admin <noreply@popory.local>` (bot identity, 메시지에 실제 actor email 명시) |

## 4. 아키텍처

```
portal /admin/brief-categories                 launchd 09:00 KST
         │                                              │
         │  GET/PUT (cookie+role=admin)                 │
         ▼                                              │
 popory-api-prod Worker                                 │
 /api/admin/brief-categories[/{slug}]                   │
         │                                              │
         │  GitHub Contents API REST                    │
         │  Authorization: Bearer ${BRIEF_CATEGORIES_GITHUB_TOKEN}  │
         ▼                                              │
 GitHub rarebirds-svg/popory                            │
 services/brief/categories/{slug}/SKILL.md  ←─ git ─────┤
                                                        │
                                              run_daily.sh
                                              ① git pull --ff-only origin main
                                              ② categories.list_categories() 스캔
                                              ③ generate/publish/send
```

git이 portal·Mac 자동화 사이의 단일 진실 매개체. portal admin은 git에 쓰고, launchd는 git에서 읽는다.

## 5. portal admin UI

### 5.1 목록 페이지 `/admin/brief-categories`

테이블 형식. 컬럼 — slug, name, mode, enabled, 마지막 수정 (commit sha 짧게 + relative time), [편집] 링크.

```
slug              name        mode         enabled    last modified            
realestate        부동산      standalone   ✓          ea3130f · 2일 전         [편집]
anticorruption    반부패      bundled      ✓          ea3130f · 2일 전         [편집]
chaebol           기업집단    bundled      ✓          ea3130f · 2일 전         [편집]
sanction          Sanction    bundled      ✓          ea3130f · 2일 전         [편집]
antitrust         공정거래    bundled      ✓          ea3130f · 2일 전         [편집]
```

데이터. worker route GET `/api/admin/brief-categories` → GitHub Contents API list (`categories/`) → 각 SKILL.md GET → frontmatter 파싱 → JSON.

### 5.2 편집 페이지 `/admin/brief-categories/{slug}`

상단 헤더 — slug · 마지막 수정 (sha · author · date).

폼 필드 (모두 server-validate).
- `name` (string, 한국어 표시명)
- `slug` (read-only, URL 일치 보장)
- `delivery_mode` (select. `standalone` / `bundled`)
- `subject_template` (string, `{name}`·`{date}` placeholder 허용)
- `sender_name` (string)
- `enabled` (checkbox)
- `system_prompt` (textarea, 모노스페이스, 30~40줄 높이)

하단 — [저장] 버튼 · [취소] 링크 (목록으로). 저장 시 PUT 요청 + `sha` (form hidden field) 포함.

폼 client-side 검증.
- slug regex `^[a-z][a-z0-9-]{1,30}$` (read-only라 위반 안 일어남)
- delivery_mode 화이트리스트
- name·subject_template·sender_name 비어있지 않음
- system_prompt 최소 100자

server-side에서 동일 검증 + 추가로 commit 시점 SHA 검사.

## 6. portal API (Cloudflare Worker)

### 6.1 신규 라우트
`workers/api/src/routes/admin_brief_categories.ts`.

| Method · Path | 동작 |
|---|---|
| GET `/api/admin/brief-categories` | 카테고리 목록 (간략. slug·name·delivery_mode·enabled·last_modified) |
| GET `/api/admin/brief-categories/:slug` | 단건 (frontmatter 6필드 + system_prompt + `sha` for optimistic locking) |
| PUT `/api/admin/brief-categories/:slug` | 단건 저장 (request body. 6필드 + system_prompt + `sha`) |

모든 라우트. `role=admin` 검사. 비admin → 401.

### 6.2 GitHub Contents API 호출

list. `GET /repos/rarebirds-svg/popory/contents/services/brief/categories`
single. `GET /repos/rarebirds-svg/popory/contents/services/brief/categories/{slug}/SKILL.md`
update. `PUT /repos/rarebirds-svg/popory/contents/services/brief/categories/{slug}/SKILL.md`

PUT body.
```json
{
  "message": "chore(brief): update categories/{slug}/SKILL.md via portal admin (by {actor_email})",
  "content": "<base64 encoded SKILL.md>",
  "sha": "<existing blob sha>",
  "branch": "main",
  "committer": { "name": "popory-portal-admin", "email": "noreply@popory.local" },
  "author":    { "name": "popory-portal-admin", "email": "noreply@popory.local" }
}
```

(commit author 이메일을 admin user의 실제 이메일로 두는 옵션도 있지만, 그러면 GitHub user resolution 시 의도치 않은 mention 발생 가능. bot identity 사용 + commit body에 actor 명시가 안전.)

`{actor_email}`은 worker route가 cookie session으로 resolve한 `SessionUser.email` 사용. 비admin은 401로 차단되므로 항상 admin user의 email.

### 6.3 SKILL.md 직렬화

server에서 frontmatter + body를 다음 포맷으로 결합 (현재 SKILL.md 구조와 동일).

```
---
slug: {slug}
name: {name}
delivery_mode: {delivery_mode}
subject_template: "{subject_template}"
sender_name: "{sender_name}"
enabled: {true|false}
---

{system_prompt}
```

따옴표 처리 — `subject_template`과 `sender_name`은 `{`·`}` 같은 YAML special char를 포함하므로 항상 큰따옴표 wrap. value 안의 `"`는 `\"` escape.

## 7. launchd 적용 (services/brief/run_daily.sh)

`start dry_run=...` log 직후, secrets source 이전 단계에 다음 한 줄 추가.

```bash
# 0) git pull — portal admin이 GitHub에 commit한 SKILL.md 변경을 가져옴
GIT_PULL_OUT=$(git -C "${BRIEF_DIR}/.." pull --ff-only origin main 2>&1)
GIT_PULL_EXIT=$?
log "\"git pull exit=${GIT_PULL_EXIT}\""
echo "${GIT_PULL_OUT}" >> "${LOG_FILE}"
# 실패해도 진행 (기존 SKILL.md로). conflict나 dirty tree면 운영자 review 필요.
```

`${BRIEF_DIR}` = `/Users/daegong/projects/popory/services/brief`. `${BRIEF_DIR}/..` = popory monorepo root. fast-forward 전용. 충돌 시 fail이지만 본문 흐름은 진행.

## 8. 인증·secrets

### 8.1 PAT
- 형식. Fine-grained Personal Access Token
- 권한 범위. `rarebirds-svg/popory` 단일 repo
- 권한 항목. `Contents: Read and write` (다른 항목 모두 No access)
- 만료. 90일 권장 (만료 시 admin에서 401 → 운영자 재발급)
- 발급자. GitHub user `rarebirds-svg` (사용자 본인)

### 8.2 Cloudflare Pages secret
`BRIEF_CATEGORIES_GITHUB_TOKEN`. wrangler 또는 Cloudflare dashboard로 등록.

Worker에서 `env.BRIEF_CATEGORIES_GITHUB_TOKEN` 으로 접근.

### 8.3 portal admin 권한
기존 `role=admin` 검사 (lib/session.ts) 그대로 활용. 새 로직 추가 없음.

## 9. Error handling

| 실패 지점 | 처리 |
|---|---|
| GitHub Contents API 401·403 | admin 응답 502 + 메시지 `"GitHub 인증 실패 — BRIEF_CATEGORIES_GITHUB_TOKEN 확인"` |
| GitHub rate limit (403 with x-ratelimit-remaining=0) | admin 응답 503 + 메시지 `"GitHub rate limit 도달 — 잠시 후 재시도"` |
| GitHub 409 (sha mismatch, 다른 사람이 그 사이 수정) | admin 응답 409 + 메시지 + 폼이 자동 reload (최신 sha + 본문) |
| validate 실패 (server-side) | admin 응답 422 + 필드별 오류 메시지 |
| PUT 후 GitHub 5xx | admin 응답 502 + 메시지 `"GitHub 저장 실패 — 잠시 후 재시도"` |
| 비admin 접근 | 401 |
| launchd `git pull` fast-forward 거부 (local change 충돌) | `run_daily.sh` log에 fail 기록 + 기존 SKILL.md로 generate 진행 (장애 격리). 운영자 수동 정리 필요 |

## 10. Testing

### 10.1 worker route 단위 (`workers/api/tests/admin_brief_categories.test.ts`)
- GET 목록. GitHub API mock → 5개 카테고리 frontmatter 파싱 → 예상 JSON
- GET 단건. mock → frontmatter 6필드 + body + sha 반환
- PUT 정상. sha 일치 + validate 통과 → GitHub PUT mock 호출 검증 (body·base64·sha)
- PUT sha mismatch. mock 409 → 라우트 409 + 최신 본문 응답
- PUT validate 실패 (slug 위반 등) → 422
- 비admin → 401

### 10.2 portal page 통합 (Playwright)
- admin role login → `/admin/brief-categories` 목록 5개 렌더
- `[편집]` 클릭 → `/admin/brief-categories/realestate` 폼 7필드 모두 prefill
- 폼 submit → 성공 토스트 + 목록 redirect

### 10.3 launchd `git pull` smoke
`run_daily.sh --dry-run` 실행 시 log에 `git pull exit=0` 라인 + working tree 변동 없음 확인.

## 11. Migration / 운영 절차

배포 순서.
1. GitHub Fine-grained PAT 발급 (사용자 작업, 콘솔)
2. wrangler로 Cloudflare Pages secret 등록. `pnpm --filter @popory/portal exec wrangler pages secret put BRIEF_CATEGORIES_GITHUB_TOKEN --project-name=popory-portal`
3. worker route + portal page 신규 코드 commit + deploy
4. `run_daily.sh`에 `git pull` 1줄 추가 commit
5. portal admin에서 카테고리 1개 무변경 저장 → GitHub commit 1개 생성으로 흐름 검증
6. launchd 다음 09:00 KST 실행에서 git pull 정상 동작 확인

## 12. 위험 요소

- **PAT 분실/유출.** GitHub repo 쓰기 권한이라 유출 시 악의적 commit 위험. → 90일 만료 + 단일 repo scope로 격리. Cloudflare secret이라 GitHub repo에 평문 노출 없음.
- **launchd git pull 실패.** local uncommitted change 또는 conflict가 있으면 fast-forward 거부 → 그날 SKILL.md 변경 미반영. → log에 명시 기록, 운영자가 매일 또는 발견 시 정리. (개발 중 IDE 자동 저장이 dirty tree 만들 수 있음. CLAUDE 자동화는 단위 작업마다 commit하므로 위험 낮음)
- **GitHub API rate limit.** 인증된 fine-grained PAT는 시간당 5000 req. admin 사용량 낮으므로 실질적 영향 없음. 다만 list endpoint는 카테고리 수만큼 GET 호출 누적 — 5개라 25 req 정도. 안전.
- **SHA 충돌.** 동시 편집은 단일 운영자 환경이라 거의 안 일어남. 그래도 optimistic locking으로 데이터 손실 방지.
- **frontmatter validate 우회.** 만약 server-side validate가 빠지면 잘못된 SKILL.md가 commit되어 launchd 실행 fail 위험. → server-side validate 반드시 PUT 처리 전 적용. 단위 테스트로 보장.

## 13. 향후 확장 여지 (본 spec 범위 밖)

- 카테고리 추가/삭제 UI (`POST/DELETE /api/admin/brief-categories`)
- 편집 이력 (GitHub commits API 결과를 admin에 표시)
- 라이브 미리보기 (markdown 렌더)
- 카테고리별 편집자 권한 분리
- frontmatter spec 변경 시 마이그레이션 도우미
