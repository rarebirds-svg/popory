<!-- 부동산 일일 브리핑 routine이 매일 fetch하는 매뉴얼. PEM 등 secret은 routine prompt에서 inject. -->

# 부동산 이슈 데일리 브리핑 매뉴얼

> **이 매뉴얼은 cloud routine이 매일 fetch한다.** routine prompt는 이 URL과 inject할 secret만 담고, 절차는 모두 여기에 산다. 매뉴얼을 수정하려면 popory main에 push하면 다음 routine 실행부터 즉시 반영된다.
>
> **secret inject 규약.** 매뉴얼의 `<<<PRIVATE_PEM_FROM_ROUTINE_PROMPT>>>` 마커는 routine prompt가 제공하는 ES256 private PEM으로 정확히 치환해 사용한다.

# 부동산 이슈 데일리 브리핑 루틴

## 1. 목적

매일 정해진 시각에 자동 실행되어, 실행일 기준 00시00분 이후 발행된 국내(수도권 중심) 부동산 관련 뉴스를 수집·정리하고 1페이지 핵심 요약을 작성·발송한다. 5분 안에 읽고 의사결정에 쓸 수 있어야 한다.

**원칙**: 사실과 출처 우선, 분석·전망 최소화.

## 2. 실행 환경

| 항목 | 값 |
|---|---|
| 실행 주기 | 스케줄 트리거 (Claude Code Routines / Cowork Scheduled) |
| 수집 윈도우 | 실행 시점 기준 KST(Asia/Seoul) 일자 00:00 이후 |
| 사용 도구 | `web_search`, `web_fetch`, `bash` (파일 저장) |
| 언어 | 한국어 |

> **시간 처리**. 시스템 시각이 UTC일 수 있다. 반드시 KST(UTC+9)로 변환한 이후 윈도우·파일·헤더 날짜를 계산할 것.
>
> **휴일 처리**. 토·일·공휴일은 Tier 1·2 보도자료 신규 발행이 거의 없다. 이 경우 통계 정기 갱신 회차 보강 또는 시장 동향 기사로 대체. 이슈 3건 미달 시 8장 절차에 따라 "이슈 부족" 안내 후 종료.

## 3. 수집 범위

### 3-1. 매체 우선순위

**Tier 1 — 정책·규제 1차 소스 (매 실행 필수 점검)**
- 국토교통부 / 기획재정부 / 금융위원회·금융감독원 / 한국은행 보도자료
- 국세청, 행정안전부 (세제 관련)
- 대한민국 정책브리핑 (부동산 정책)
- 국회 의안정보시스템, 법제처 입법예고, 국가법령정보센터
- DART 전자공시 (건설사·부동산 PF 관련)

**Tier 2 — 통계·실거래가 (매 실행 필수 점검)**
- 한국부동산원, 부동산 시장동향 모니터링 시스템(RMS)
- 국토부 실거래가 공개시스템, 부동산거래관리시스템(RTMS)
- LH한국토지주택공사
- 통계청 KOSIS, e-나라지표(주택)

**Tier 3 — 정책 연구기관 (보고서 발간 시)**
- 국토연구원, 주택산업연구원, 한국부동산연구원
- 토지주택연구원, KDI, 한국조세재정연구원, 서울연구원

**Tier 4 — 언론 (Tier 1·2 보강 또는 단독 이슈만)**
- 경제 전문지: 매일경제, 한국경제, 서울경제, 머니투데이, 이데일리
- 종합지 경제섹션 (필요 시)

### 3-2. 주제 카테고리

1. 부동산 정책·규제 (정부 발표, 세제 개편, 대출 규제)
2. 시장 동향 (매매·전세 가격, 거래량, 지역별 온도차)
3. 금융·대출 (DSR, LTV, 주담대 금리, 정책금융 상품)
4. 공급·청약 (분양 일정, 청약 경쟁률, 미분양)
5. 재건축·재개발·정비사업
6. 건설업·부동산 PF 리스크
7. 전월세 시장 (임대차법 관련 포함)
8. 부동산 관련 법·제도 변화 및 주요 판례

## 4. 이슈 선정 로직

### 4-1. 전제 조건 (전부 충족)

- 인용 기사의 **게재일이 KST 기준 실행일자와 동일** (발표일·정책일 아님). 예외는 4-4.
- 위 주제 카테고리 1~8 중 하나에 해당
- Tier 1~4 매체에서 발행

### 4-2. 선정 기준 (한 가지 이상 충족)

- **영향력**. 정부·공공기관·연구기관의 공식 발표·통계 공표
- **반복성**. 2개 이상 매체에서 동일 주제 보도
- **사회적 관심도**. 댓글·공유 등 독자 반응이 활발한 사안

### 4-3. 제외 기준

- 단순 분양 광고성 기사
- 특정 단지·매물 홍보 기사
- 1개 매체에서만 다룬 단발성·가십성 기사
- 기관 보도자료 단순 재게재 (원문이 Tier 1에 있으면 원문으로 대체)
- 게재일이 실행일과 다른 기사 → 상세 절차 **4-4**
- 과거 14일 이내 이미 브리핑한 사안과 동일 주제 → 상세 절차 **4-5**

### 4-4. 출처 링크 게재일 검증 (필수)

**원칙**: "오늘의 시점에 의미 있는 사안" ≠ "오늘 게재된 기사". 본문에서 다루는 사안이 며칠 전 발표 정책이라도, *인용 URL은 실행일 게재 기사*여야 한다. 발표 당일 기사를 그대로 재인용하면 탈락.

**검증 절차 (출처 URL 1건마다 적용)**

1. URL 슬러그의 `YYYYMMDD` 또는 `YYYY-MM-DD` 패턴 확인 (대다수 한국 언론사 URL이 이 형식 — 예. `ajunews.com/view/20260512175501631`, `newspim.com/news/view/20260515001231`).
   - 슬러그 날짜 ≠ 실행일자 → **즉시 탈락**. 후속 기사로 교체.
2. 슬러그에 날짜가 없으면 `web_fetch`로 페이지 메타(`<time>`, `article:published_time`, 본문 헤더 일자)를 읽어 실행일과 대조.
3. 메타로도 확인 불가하면 그 링크는 **사용하지 않는다**. "확인 불가 = 탈락". 추정 금지.

**예외 (실행일 게재가 아니어도 인용 가능)**

| 유형 | 조건 |
|---|---|
| 정적 통계·시스템 페이지 | 한국부동산원 R-ONE, 청약홈 캘린더, 국토부 실거래가 시스템 등 상시 갱신 페이지. 본문에 인용 수치가 실행일자에 갱신된 회차임을 확인하고 **회차 일자 명시** (예. "한국부동산원 주간동향 2026년 5월 둘째 주") |
| 정부 보도자료 원문 페이지 | 국토부·기재부·금융위·한국은행 등 1차 소스. 발표일이 며칠 전이어도 인용 가능, 단 **발표일 명시** (예. "국토부 2026-05-12 발표") |

**Tier 4 언론 기사는 예외 없이 실행일 게재본만 허용.** 개인 블로그(`aboda.kr`, `mhb-blog.com`, 티스토리·네이버 블로그 등)는 게재일 확인이 곤란하고 신뢰도가 낮으므로, *Tier 1~4 정식 매체의 동일 사실 오늘자 기사가 확보된 경우에만 보조 인용* 가능. 단독 출처 사용 금지.

### 4-5. 과거 브리핑 주제 중복 제외 (Phase B 동안 일시 비활성)

> **Phase B (2026-05-29~)**: cloud sandbox는 매 invocation 새로 시작돼 Mac 로컬 archive 파일에 접근할 수 없다. 본 §4-5 절차는 **Phase B 동안 전부 skip 한다**. 중복 검사 없이 §4-1·§4-2·§4-3·§4-4만 적용한다. Phase C에서 archive를 portal API 또는 다른 cloud 저장소로 옮긴 뒤 재활성한다.

### 4-5 (참고용 — Phase C 복원 시 사용). 과거 브리핑 주제 중복 제외 (Phase C에서 재활성)

**원칙**: 최근 14일 이내 다룬 주제는 *그날의 신규 사실*이 없으면 재인용하지 않는다. 매일 같은 정책 해설·같은 시장 진단을 반복하면 브리핑 정보가치가 사라진다.

#### 4-5-1. 아카이브 메커니즘

- **위치**. `/Users/daegong/projects/daily-brief/archive/topics.jsonl`
- **포맷**. 한 줄 = JSON 1건. 매 실행 발송 성공 후 그날 다룬 이슈마다 append.
  ```json
  {"date":"2026-05-15","section":"core","title":"정부, 토지거래허가구역 실거주 의무 유예 확대","keywords":["토지거래허가구역","실거주 유예","임대차계약","무주택","시행령 입법예고"]}
  ```
- **필드 정의**
  - `date`. 실행일자 (KST, `YYYY-MM-DD`)
  - `section`. `"core"` (핵심 이슈) 또는 `"monitor"` (추가 모니터링)
  - `title`. 본문 h4 제목 그대로
  - `keywords`. 5~8개. 정책명·법안명·기관명·핵심 통계명·지역명 등 *식별성 있는 키워드*만. "부동산", "정부", "시장", "오늘" 같은 불용어 제외.
- 디렉터리·파일이 없으면 매 실행 첫 단계에서 생성:
  ```bash
  mkdir -p /Users/daegong/projects/daily-brief/archive
  touch /Users/daegong/projects/daily-brief/archive/topics.jsonl
  ```

#### 4-5-2. 중복 검사 절차 (후보 이슈 확정 직전 적용)

1. archive `topics.jsonl` 마지막 14일치(실행일 -1 ~ -14)를 조회:
   ```bash
   awk -v from="$(TZ=Asia/Seoul date -v-14d +%Y-%m-%d)" -v to="$(TZ=Asia/Seoul date -v-1d +%Y-%m-%d)" \
     -F'"date":"' 'NF>1 { split($2, a, "\""); if (a[1] >= from && a[1] <= to) print }' \
     /Users/daegong/projects/daily-brief/archive/topics.jsonl
   ```
   파일이 비어 있으면 검사 생략 (첫 실행).
2. 각 후보 이슈에 5~8개 키워드를 사전 추출 → archive 키워드와 대조.
3. **2개 이상 키워드가 겹치면 동일 주제 후보**로 간주.
4. 동일 주제 후보는 다음 중 *하나* 충족 시에만 통과:
   - **새로운 통계 회차** — 한국부동산원 주간동향·KOSIS 정기 통계 등 *주간·월간 정기 갱신*
   - **새로운 정책 단계** — 발표 → 입법예고, 입법예고 → 시행, 시행 → 후속 개정, 법안 발의 → 국회 통과 등 상태 변화
   - **새로운 결정·승인·집행** — 신규 인허가, 첫 청약 결과, 정책 시행 후 첫 통계, 첫 행정처분 등

   미충족 시 **탈락**. 다른 이슈로 교체.
5. 통과한 이슈는 본문에 `*최근 브리핑(YYYY-MM-DD)에서 다룬 주제의 진전*`을 시사점 1줄로 명시.

#### 4-5-3. 발송 후 아카이브 갱신

발송 성공(exit 0) 직후 그날의 모든 이슈를 jsonl에 append. 발송 실패 시 append 금지.

```bash
cat >> /Users/daegong/projects/daily-brief/archive/topics.jsonl <<'EOF'
{"date":"YYYY-MM-DD","section":"core","title":"...","keywords":["...","..."]}
{"date":"YYYY-MM-DD","section":"core","title":"...","keywords":["...","..."]}
{"date":"YYYY-MM-DD","section":"monitor","title":"...","keywords":["...","..."]}
EOF
```

## 5. 출력 형식

본문은 Gmail로 발송됨과 동시에 사용자가 본문을 복사해 네이버 블로그에 붙여넣어 포스팅에 활용한다. 두 환경(메일 + 블로그) 모두에서 가독성과 강조가 유지되어야 한다.

### 5-1. 디자인 원칙

**HTML 호환성**

1. **인라인 스타일만 사용**. `<style>` 블록·CSS 클래스 금지.
2. **보수적 속성에만 의존**. `color`, `font-weight`, `font-size`, `text-decoration`만 안전. `background`·`border`·`max-width`·`font-family`는 보강용으로만 사용 (없어져도 의미가 살아남게).
3. **링크 인라인 스타일**. 모든 `<a>`에 `style="color:#0645ad; text-decoration:underline;"`.
4. **모바일 대응**. `<head>`에 viewport meta, body font-size 16px 기본.
5. **블로그 계층 호환**. 본문은 `<h2>`부터 시작 (블로그 H1은 자체 제목이 차지).

**시각 위계**

6. **텍스트 기호 이중화**. `■`(핵심)·`▶`(모니터링)·`─────`(구분) 글리프 사용. 인라인 스타일이 stripped되어도 시각 위계 유지.
7. **이슈 제목(h4) 강화**. 좌측 컬러 바 + bold + 17px 인라인 명시.
8. **핵심 정보 `<strong>` 처리**. 모든 통계 수치·백분율·날짜·지역명·정책명·기관명을 `<strong>`으로 감싼다 (색상이 빠져도 굵기는 살아남음).
9. **출처 형식 통일**. 핵심·모니터링 섹션 모두 동일한 `<ul><li><a>` 구조.
10. **블로그 활용 보강**. 본문 끝에 그날 토픽 기반 해시태그 5~7개.

### 5-2. 구조 템플릿

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>[부동산 이슈 브리핑] YYYY-MM-DD</title>
</head>
<body style="font-size:16px; line-height:1.7; color:#222;">

<h2 style="font-size:22px; color:#111; border-bottom:2px solid #333; padding-bottom:6px; margin-bottom:8px;">
  [부동산 이슈 브리핑] YYYY-MM-DD <span style="color:#888; font-size:14px;">(KST 기준)</span>
</h2>

<p style="color:#666; font-size:14px; margin-top:0;">
  수집 윈도우. YYYY-MM-DD HH:MM ~ YYYY-MM-DD HH:MM KST<br>
  ※ 사실과 출처 우선, 분석·전망 최소화.
</p>

<h3 style="font-size:18px; color:#c00; border-left:4px solid #c00; padding-left:10px; margin:30px 0 12px;">
  ■ 오늘의 핵심 이슈
</h3>

<h4 style="font-size:17px; color:#111; border-left:3px solid #c00; padding-left:10px; line-height:1.4; margin:24px 0 8px;">
  1. (이슈 제목 — 한 줄 요약)
</h4>
<ul style="margin:0 0 16px 20px; padding:0;">
  <li style="margin-bottom:6px;">
    <strong style="color:#555;">핵심 내용.</strong>
    사실 중심 3~5문장. 모든 수치/날짜/고유명사는 <strong>이렇게</strong> 강조.
    예. <strong>2026년 5월 9일</strong> 자로 <strong>다주택자 양도세 중과 유예</strong>가 종료된다.
  </li>
  <li style="margin-bottom:6px;">
    <strong style="color:#555;">시사점.</strong> 시장·정책·법제 측면 함의 1~2문장.
  </li>
  <li>
    <strong style="color:#555;">출처.</strong>
    <ul style="margin:4px 0 0 16px;">
      <li><a href="https://..." style="color:#0645ad; text-decoration:underline;">[매체명] 기사 제목</a></li>
      <li><a href="https://..." style="color:#0645ad; text-decoration:underline;">[매체명] 기사 제목</a></li>
    </ul>
  </li>
</ul>

<!-- 이슈 2, 3, 4 동일 형식 반복 -->

<h3 style="font-size:18px; color:#666; border-left:4px solid #888; padding-left:10px; margin:32px 0 12px;">
  ▶ 추가 모니터링 이슈
</h3>

<h4 style="font-size:16px; color:#222; border-left:3px solid #888; padding-left:10px; line-height:1.4; margin:20px 0 6px;">
  (모니터링 이슈 제목)
</h4>
<ul style="margin:0 0 14px 20px;">
  <li style="margin-bottom:6px;"><strong style="color:#555;">요약.</strong> 1~2문장.</li>
  <li>
    <strong style="color:#555;">출처.</strong>
    <ul style="margin:4px 0 0 16px;">
      <li><a href="https://..." style="color:#0645ad; text-decoration:underline;">[기관/매체명] 페이지·기사 제목</a></li>
    </ul>
  </li>
</ul>

<hr style="margin:32px 0 16px; border:none; border-top:1px solid #ddd;">

<p style="font-size:14px; color:#555; margin:0 0 8px;">
  <strong>관련 태그.</strong> #부동산 #(그날 토픽 기반 자동 생성 태그 5~7개)
</p>

<p style="font-size:12px; color:#888; margin:0;">
  자동 생성. Claude Code 부동산 브리핑 / 출처는 각 기사 링크 참조<br>
  생성시각. YYYY-MM-DD HH:MM KST
</p>

</body>
</html>
```

### 5-3. publish용 Markdown 본문 (Phase B · 필수)

> **이 단계는 옵션이 아니다.** 메일용 HTML 본문 작성과 동시에 반드시 수행한다. 본문 파일 `/tmp/brief_${DATE}.md` 와 메타 파일 `/tmp/brief_${DATE}.meta.json` 이 생성돼 있어야 §7-bis가 동작한다. 두 파일이 없으면 publish 자체가 불가능하므로 §5-3은 건너뛰지 말 것.

메일용 HTML 본문(§5-1·§5-2)과 함께, 같은 내용을 **GFM Markdown 1부**로 작성해 portal publish에 사용한다.

규칙.

- H1(`#`) 두지 않는다. 제목은 메타 파일에 따로 둔다(`/p/brief/<id>` 페이지가 그 제목을 H1로 렌더).
- §5-2 HTML 위계를 다음과 같이 1:1 옮긴다.
  - `<h3>■ 오늘의 핵심 이슈` → `## ■ 오늘의 핵심 이슈`
  - `<h3>▶ 추가 모니터링 이슈` → `## ▶ 추가 모니터링 이슈`
  - 이슈 `<h4>` → `### 1. 이슈 제목`
  - `<ul><li>` → `- `
  - `<strong>...</strong>` → `**...**`
  - `<a href="URL">텍스트</a>` → `[텍스트](URL)`
- 인라인 스타일·색·border bar는 모두 생략한다. 강조는 `**...**` 만 사용.
- 본문 끝 해시태그 줄·푸터(생성시각)는 그대로 옮긴다.
- 표·체크리스트가 필요하면 GFM 문법 그대로 (`| a | b |`, `- [ ]`).

파일 작성. Write tool 금지·Bash heredoc 사용 (§7 안전 수칙 동일).

```bash
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
cat > /tmp/brief_${DATE}.md <<'EOF'
## ■ 오늘의 핵심 이슈

### 1. (이슈 제목 — 한 줄 요약)

- **핵심 내용.** 사실 중심 3~5문장. 모든 수치/날짜/고유명사는 **이렇게** 강조.
- **시사점.** 시장·정책·법제 측면 함의 1~2문장.
- **출처.**
  - [[매체명] 기사 제목](https://...)
  - [[매체명] 기사 제목](https://...)

### 2. ...

## ▶ 추가 모니터링 이슈

### (모니터링 이슈 제목)

- **요약.** 1~2문장.
- **출처.**
  - [[기관/매체명] 페이지·기사 제목](https://...)

---

**관련 태그.** #부동산 #(그날 토픽 5~7개)

*자동 생성. Claude Code 부동산 브리핑*
*생성시각. YYYY-MM-DD HH:MM KST*
EOF
```

메타 작성 (publish 시 필수). `title`은 §5-2 메일 subject와 동일 문구.

```bash
PUBLISHED_AT=$(TZ=Asia/Seoul date +%s)
cat > /tmp/brief_${DATE}.meta.json <<EOF
{
  "title": "[부동산 이슈 브리핑] ${DATE}",
  "summary": "오늘의 핵심 이슈 N건 + 추가 모니터링 M건",
  "tags": ["부동산","정책","시장동향"],
  "published_at": ${PUBLISHED_AT}
}
EOF
```

`tags`는 그날 토픽 기반 5~7개. 각 40자 이하, 최대 20개. `summary`는 메일 첫 줄 요약과 동일.

### 5-4. 발송 전 self-check (전부 통과해야 발송)

**HTML 구조**
- [ ] `<head>`에 viewport meta 포함
- [ ] 모든 `<a>` 태그에 inline style (color + underline) 명시
- [ ] h3·h4 모두 좌측 border bar + 글리프(■/▶) 표시
- [ ] 출처 표시가 핵심·모니터링 섹션 모두 동일한 `<ul><li><a>` 구조
- [ ] 본문이 `max-width`·`font-family`에 핵심 정보 표현을 의존하지 않음 (블로그 복붙 호환)
- [ ] 본문 끝에 해시태그 1줄 + 자동 생성 푸터

**콘텐츠 강조**
- [ ] 모든 통계 수치·백분율·날짜·지역명·정책명·기관명이 `<strong>`으로 감싸짐

**출처 검증 (4-4 절차)**
- [ ] 인용한 모든 언론사 기사(Tier 4)의 URL 게재일이 실행일자와 일치 — 슬러그·메타 둘 다 확인
- [ ] 정적 통계 페이지 인용 시 본문에 인용 회차 일자 명시 (예. "한국부동산원 주간동향 2026년 5월 둘째 주")
- [ ] 정부 보도자료 원문 인용 시 본문에 발표일 명시 (예. "국토부 2026-05-12 발표")
- [ ] 비공식 블로그(개인 블로그·티스토리·네이버 블로그 등)를 단독 출처로 인용한 이슈 없음

**중복 검증 (4-5 절차)** — Phase B 동안 skip (cloud sandbox에 archive 없음)

**publish 본문 검증 (5-3 절차 · Phase B)**
- [ ] `/tmp/brief_${DATE}.md` 작성됨. H1 미사용, 본문에 §5-2 HTML 위계가 Markdown으로 1:1 옮겨짐
- [ ] `/tmp/brief_${DATE}.meta.json` 작성됨. `title`이 메일 subject와 동일 문구, `tags` 5~7개, `published_at`이 `TZ=Asia/Seoul date +%s` 결과

## 6. 이메일 발송 사양

| 항목 | 값 |
|---|---|
| 수신자 | lovemycho@naver.com, sungjong.kim@navercorp.com |
| 발신자 | `부동산 이슈 브리핑 <rarebirds@gmail.com>` (반드시 `--from`으로 명시) |
| 발송 방식 | **수신인별 개별 메일** (To에 1명, BCC/CC 금지) |
| 제목 | `[부동산 이슈 브리핑] YYYY-MM-DD` |
| 형식 | HTML 우선 (링크 클릭 가능), 실패 시 플레인 텍스트 |
| 재시도 | 1회 재시도 후 실패 시 로그 기록 + 사용자 알림 |

> **인코딩 주의**. `--from` 생략 시 Gmail이 계정 표시명으로 채우는데, 한글이 RFC 2047 인코딩 없이 들어가 수신측에서 모자이크(`ëŠ ìŠ` 형태)로 보인다. 호출 시 반드시 `--from "부동산 이슈 브리핑 <rarebirds@gmail.com>"`을 포함할 것.

## 7. 발송 절차 (Phase B · cloud sandbox 전용 · Gmail REST API)

> **Phase B (2026-05-29~)**: cloud sandbox는 outbound SMTP를 차단하지만 HTTPS는 허용된다. Gmail 발송은 **Gmail REST API** (`gmail.googleapis.com/gmail/v1/users/me/messages/send`)를 OAuth 2.0 refresh token으로 호출한다. credentials 3개(client_id, client_secret, refresh_token)는 routine entry prompt §3에서 inject한다.

> **자동 실행 안전 수칙**
>
> 1. 본문 HTML은 `/tmp/brief_body_${DATE}.html` 한 파일에 작성한다(수신인 공통).
> 2. 발송 스크립트는 `/tmp/brief_send.py` 한 파일에 작성한다.
> 3. 모든 파일 작성은 Bash heredoc.

### 7-1. 본문 HTML 파일 작성

§5-1·§5-2 디자인 그대로의 HTML을 한 파일에 작성한다 (수신인 공통).

```bash
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
cat > /tmp/brief_body_${DATE}.html <<'EOF'
<!DOCTYPE html>
... §5-2 HTML 전체 ...
EOF
```

### 7-2. 발송 스크립트 작성 + 3개 placeholder 치환

다음 Bash heredoc을 그대로 실행해 `/tmp/brief_send.py` 파일을 만든다. 파일 안에 OAuth 자리표시자 **3줄**이 남아 있다.

```bash
cat > /tmp/brief_send.py <<'PY_EOF'
import json, base64, sys, os, urllib.parse, urllib.request, urllib.error
from email.message import EmailMessage

CLIENT_ID = "<<<GMAIL_CLIENT_ID_FROM_ROUTINE_PROMPT>>>"
CLIENT_SECRET = "<<<GMAIL_CLIENT_SECRET_FROM_ROUTINE_PROMPT>>>"
REFRESH_TOKEN = "<<<GMAIL_REFRESH_TOKEN_FROM_ROUTINE_PROMPT>>>"

FROM_EMAIL = "rarebirds@gmail.com"
FROM_NAME = "부동산 이슈 브리핑"
RECIPIENTS = ["lovemycho@naver.com", "sungjong.kim@navercorp.com"]

data = urllib.parse.urlencode({
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "refresh_token": REFRESH_TOKEN,
    "grant_type": "refresh_token",
}).encode()
try:
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=data, timeout=30) as resp:
        access_token = json.loads(resp.read().decode())["access_token"]
except urllib.error.HTTPError as e:
    print(f"oauth refresh failed: HTTP {e.code} {e.read().decode(errors='replace')[:300]}", file=sys.stderr)
    sys.exit(3)

date = os.environ["BRIEF_DATE"]
subject = f"[부동산 이슈 브리핑] {date}"
html_body = open(f"/tmp/brief_body_{date}.html", encoding="utf-8").read()

results = {"sent": 0, "failed": 0, "message_ids": {}, "errors": {}}

for to in RECIPIENTS:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"] = to
    msg.set_content("HTML 본문 미지원 클라이언트용 fallback")
    msg.add_alternative(html_body, subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    req = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": raw}).encode(),
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            r = json.loads(resp.read().decode())
            results["sent"] += 1
            results["message_ids"][to] = r.get("id")
    except urllib.error.HTTPError as e:
        results["failed"] += 1
        results["errors"][to] = f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}"
    except Exception as e:
        results["failed"] += 1
        results["errors"][to] = str(e)

print(json.dumps(results, ensure_ascii=False))
PY_EOF
```

heredoc 실행 후 routine은 **Edit 또는 Read+Write 도구로 `/tmp/brief_send.py` 파일을 열어 3개 placeholder를 모두 치환**한다.

| 매뉴얼 placeholder | routine entry prompt §3에서 가져올 값 |
|--------------------|----------------------------------------|
| `<<<GMAIL_CLIENT_ID_FROM_ROUTINE_PROMPT>>>` | `client_id` 한 줄 |
| `<<<GMAIL_CLIENT_SECRET_FROM_ROUTINE_PROMPT>>>` | `client_secret` 한 줄 |
| `<<<GMAIL_REFRESH_TOKEN_FROM_ROUTINE_PROMPT>>>` | `refresh_token` 한 줄 |

치환 후 세 변수가 모두 entry prompt의 실제 값을 포함한 형태가 되어야 한다.

### 7-3. 실행 + 결과 처리

```bash
export BRIEF_DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
python3 /tmp/brief_send.py
```

stdout JSON 한 줄. 형식: `{"sent":N,"failed":M,"message_ids":{...},"errors":{...}}`.

- `sent ≥ 1` → §7-bis publish **진행**.
- `sent == 0` → §7-bis publish **건너뛴다** (메일 0건이면 공개본도 안 만든다).

exit 3 = OAuth refresh 실패. credentials 무효 또는 만료. routine 즉시 종료.

### 7-4. 아카이브 갱신 — Phase B 동안 skip

### 7-bis. Phase B publish — 별도 top-level 섹션 (§7-bis) 참조. `sent ≥ 1` 일 때만 수행.

### 7-5. 발송 요약 보고

stdout에 다음 JSON 한 줄을 print 후 종료한다.

```
{"date":"YYYY-MM-DD","sent":N,"failed":M,"message_ids":{...},"publish_id":"..."}
```

- `sent`/`failed`/`message_ids`: §7-3 결과.
- `publish_id`: §7-bis-3 출력. publish 미수행 또는 실패 시 `null` 또는 실패 사유.

### Exit code 처리

| Code | 의미 | 조치 |
|---|---|---|
| 0 | 성공 | message_id 로그 기록 |
| 2 | token.json 없음 | `auth_setup.py` 실행 안내 |
| 3 | 토큰 폐기 | `auth_setup.py` 재실행 안내 |
| 4 | Gmail API 4xx | 재시도 안 함. 수신인·본문·할당량 점검 |
| 5 | Gmail API 5xx 또는 기타 | 1회 재시도 후 실패 시 네트워크·Gmail 상태 점검 |

> 발송 검증은 logs 파일 마지막 줄 읽기로 갈음한다 (`search_threads`/`list_drafts` MCP 불필요).

## 7-bis. Phase B publish (top-level · 필수)

> **본 섹션은 §7-4-bis에서 redirect된 것이다.** 메일 발송이 끝나면 7-bis-1·7-bis-2·7-bis-3 **세 단계 모두**를 반드시 수행한 뒤 §7-5로 돌아간다. §7-bis를 건너뛰는 것은 routine 실패다. 실행 결과(성공·실패)는 §7-5 발송 요약 보고에 publish_id 또는 실패 사유로 명시한다.

§7 메일 발송이 모두 끝난 뒤 본 섹션의 3단계를 그대로 실행한다. routine 종료 직전 1회. 실패해도 메일에는 영향 없다(메일은 이미 발송 완료).

이 절차는 list 아이템 안 깊은 들여쓰기가 발생하지 않도록 모든 코드 블록이 top-level 0-공백으로 작성되어 있다. 들여쓰기를 임의로 추가하지 말 것.

### 7-bis-0. 본문 파일 존재 점검 (선결 조건)

§5-3에서 작성됐어야 할 두 파일이 실제로 존재하는지 다음 Bash로 확인한다.

```bash
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
ls -la /tmp/brief_${DATE}.md /tmp/brief_${DATE}.meta.json
```

둘 중 하나라도 없으면 routine은 §5-3으로 돌아가 본문 + 메타 파일을 즉시 작성한 뒤 다시 §7-bis로 진입한다. 본문 파일 없이는 publish가 불가능하다.

### 7-bis-1. 환경변수 export

다음 Bash를 그대로 실행한다.

```bash
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
export BRIEF_BODY_FILE=/tmp/brief_${DATE}.md
export BRIEF_META_FILE=/tmp/brief_${DATE}.meta.json
```

### 7-bis-2. Python 스크립트 작성 후 PEM placeholder 치환

다음 Bash heredoc을 그대로 실행해 `/tmp/brief_publish.py` 파일을 만든다. 파일 안에는 일부러 PEM 자리 표시자 한 줄(`<<<PRIVATE_PEM_FROM_ROUTINE_PROMPT>>>`)이 남아 있다.

```bash
cat > /tmp/brief_publish.py <<'PY_EOF'
import json, time, base64, os, urllib.request, urllib.error, subprocess, sys

PRIVATE_PEM = b"""-----BEGIN PRIVATE KEY-----
<<<PRIVATE_PEM_FROM_ROUTINE_PROMPT>>>
-----END PRIVATE KEY-----
"""
KID = "services-brief-2026-05"
PORTAL_BASE = "https://api.poporyfamily.com"

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "cryptography"])
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils

def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

key = serialization.load_pem_private_key(PRIVATE_PEM, password=None)
now = int(time.time())
header = {"alg": "ES256", "kid": KID, "typ": "JWT"}
claims = {"iss": "popory-portal", "aud": "popory-portal", "sub": "services-brief",
          "email": "services-brief@popory.local", "area": "brief",
          "iat": now, "exp": now + 60}
signing_input = (b64u(json.dumps(header, separators=(",", ":")).encode()) + "." +
                 b64u(json.dumps(claims, separators=(",", ":")).encode())).encode()
der_sig = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
r, s = utils.decode_dss_signature(der_sig)
raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
jwt_token = signing_input.decode() + "." + b64u(raw_sig)

body = open(os.environ["BRIEF_BODY_FILE"], encoding="utf-8").read()
meta = json.loads(open(os.environ["BRIEF_META_FILE"], encoding="utf-8").read())
payload = {"area": "brief", "title": meta["title"], "body": body,
           "published_at": int(meta["published_at"])}
if meta.get("summary"): payload["summary"] = meta["summary"]
if meta.get("tags"): payload["tags"] = list(meta["tags"])

req = urllib.request.Request(
    f"{PORTAL_BASE}/api/published_items",
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
        print(json.dumps({"status": "ok", "publish_id": result.get("id")},
                         ensure_ascii=False))
except urllib.error.HTTPError as e:
    print(f"publish failed: HTTP {e.code} {e.read().decode(errors='replace')}",
          file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"publish error: {e}", file=sys.stderr)
    sys.exit(2)
PY_EOF
```

heredoc 실행 후 routine은 **Edit 또는 Read+Write 도구로 `/tmp/brief_publish.py` 파일을 열어** `<<<PRIVATE_PEM_FROM_ROUTINE_PROMPT>>>` 한 줄을 **routine entry prompt §2의 PEM 본문(BEGIN/END 헤더 줄 사이의 base64 본문 모든 줄)** 으로 정확히 치환한다.

PEM 본문은 보통 3줄이다. entry prompt의 다음 부분에서 가져온다.

```
-----BEGIN PRIVATE KEY-----
<여기 3줄의 base64 본문이 PEM 본문>
-----END PRIVATE KEY-----
```

치환 후 `/tmp/brief_publish.py` 의 `PRIVATE_PEM` 변수가 다음 형태가 되어야 한다.

```
PRIVATE_PEM = b"""-----BEGIN PRIVATE KEY-----
<3줄의 base64 본문>
-----END PRIVATE KEY-----
"""
```

### 7-bis-3. 실행

```bash
python3 /tmp/brief_publish.py
```

성공 시 stdout JSON 한 줄. 형식: `{"status":"ok","publish_id":"<ulid>"}`. `publish_id` 를 §7-5 발송 요약 보고에 추가한다.

실패 시 stderr 에 사유. exit code:
- 1 = portal HTTP 4xx/5xx (인증·payload·서버 오류)
- 2 = 기타 (Python 예외, 네트워크 오류 등)

실패해도 그날 작업은 정상 종료한다 — 메일은 이미 발송됐기 때문. 운영자가 다음 routine 실행 전 `/p/brief/` 와 stderr 메시지를 확인한다.

## 8. 실행 체크리스트

1. 현재 KST 시각 확인 → 24시간 수집 윈도우 계산
2. Tier 1·2 매체 접근 정상 여부 확인
3. ~~archive 디렉터리·파일 존재 확인~~ — Phase B 동안 skip
4. ~~archive 최근 14일치 조회 → 중복 필터링~~ — Phase B 동안 skip
5. 전제 조건·선정 기준 적용 후 이슈 3건 이상 확보. 미달 시 "이슈 부족" 안내 후 종료
6. 모든 이슈에 원본 URL 포함 검증
7. Tier 1 1차 소스 우선 인용 여부 확인
8. 인용 URL 게재일 일괄 검증 (4-4 절차) — 슬러그·메타 둘 다 확인. 실행일 ≠ 게재일이면 교체 또는 제거. 통계 페이지·보도자료 원문은 예외, 단 본문에 회차 일자·발표일 명시
9. 5-3 publish용 Markdown 본문(`/tmp/brief_${DATE}.md`) + 메타(`/tmp/brief_${DATE}.meta.json`) 작성
10. 5-4 self-check 항목 모두 통과 확인 (HTML 메일 + publish 본문 + 출처 검증). 4-5 중복 검증은 Phase B skip.
11. 수신자 이메일 주소 정확성 재확인
12. 수신인별 1통씩 Gmail REST API 발송 (§7-2: /tmp/brief_send.py 작성 + 3개 OAuth placeholder 치환 + python3 실행)
13. ~~archive `topics.jsonl` append~~ — Phase B 동안 skip
14. Phase B publish 1회 호출 (§7-bis 3단계: env export → /tmp/brief_publish.py 작성 + PEM 치환 → python3 실행). `sent ≥ 1` 일 때만 진행. exit 비제로여도 그날 작업은 정상 종료.
15. §7-5 발송 요약 JSON 출력 (sent, failed, message_ids, publish_id 포함)