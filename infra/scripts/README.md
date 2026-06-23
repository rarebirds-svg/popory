# infra/scripts

운영 보조 스크립트.

## storage-report.sh

포포리 스토리지(클라우드 + 로컬 서버) 사용량을 한 번에 실측해 표로 정리한다.

- **클라우드**: `wrangler`로 D1(`popory-portal`) 크기·테이블별 row 수, R2(`popory-portal-public`) 객체 수·용량, KV 키 수(prefix 분포)를 조회.
- **로컬 서버**: `du`로 imagegen HF 모델 캐시(`.hf`), `services/*/.venv`, `services/*/logs`, 배경음 에셋, 영상 스크래치를 측정.

```sh
# 클라우드 섹션은 wrangler 인증 필요
wrangler login            # 또는 export CLOUDFLARE_API_TOKEN=...
infra/scripts/storage-report.sh

# 옵션
infra/scripts/storage-report.sh --no-rows   # D1 테이블별 row 집계 생략
infra/scripts/storage-report.sh --no-kv     # KV 키 나열 생략
```

인증·네트워크가 없어도 로컬 디스크 섹션은 동작한다(부분 실패 허용). 권장: `jq` 설치.
