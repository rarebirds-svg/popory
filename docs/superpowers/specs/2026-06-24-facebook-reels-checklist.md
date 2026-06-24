<!-- 페이스북 릴스 배포 구현 체크리스트. -->

# 페이스북 릴스 배포 구현 체크리스트

## 백엔드 (Worker)
- [ ] `infra/migrations/0012_facebook.sql` 작성
- [ ] `workers/api/src/types.ts`에 `FACEBOOK_TOKEN_KEY` 추가
- [ ] `content_facebook.ts` (connect/callback/status/disconnect)
- [ ] `content_facebook_upload.ts` (upload/claim-upload/result)
- [ ] `app.ts`에 두 라우트 마운트
- [ ] 라우트 유닛테스트 (instagram 테스트 미러)

## 워커 (Python)
- [ ] `facebook_upload.py` (릴스 3단계 업로드)
- [ ] `worker.py` `run_facebook_upload_once` + 메인 루프 연결

## 프론트엔드 (Portal)
- [ ] `content/[id]/FacebookUpload.tsx`
- [ ] `content/facebook/page.tsx` + `DisconnectButton.tsx`
- [ ] `content/[id]/page.tsx` — facebook 필드·연결조회·버튼
- [ ] `content/new/NewJobForm.tsx` — 쇼츠 페이스북 체크박스

## 검증·배포
- [ ] `tsc --noEmit` (portal + api)
- [ ] api 유닛테스트
- [ ] `FACEBOOK_TOKEN_KEY` secret 주입 (prod)
- [ ] D1 마이그레이션 적용 (prod)
- [ ] api worker 배포 (prod)
- [ ] portal 빌드·배포 (prod)
- [ ] Meta 앱에 `pages_manage_posts` 권한 추가 (사용자 작업)
