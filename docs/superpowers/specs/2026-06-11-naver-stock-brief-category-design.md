# 네이버 주식 브리핑 카테고리 + 평일 2회·주말 1회 스케줄 설계

> 작성일 2026-06-11. 상태 승인됨(설계 단계).

## 배경

사용자가 "네이버 주식 투자"를 카테고리로 만들려 했으나, 포털에 일반 사용자용 카테고리 생성 UI가 없어 개인화 **커스텀 주제**(`area=custom-8a2c3d67b4f1`)로 등록됐다. 그 결과 두 가지 문제가 관측됐다.

1. 원래 요청한 "평일 08·18시 2회, 주말 08시 1회" 스케줄이 구현되지 않음. 커스텀 주제는 일일 배치 1회 + 온디맨드만 지원.
2. 중복 발행. 같은 날·같은 주제로 2건 발행됨. 생성 경로가 둘(온디맨드 워커 + `run_daily.sh` 일일 배치)인데 중복 방지 가드(`9c1e4d5`)가 워커 경로에만 있어, 아침 온디맨드와 일일 배치가 각각 생성해 충돌. 이전 "네이버 주식"(삭제됨) 토픽도 동일하게 2건 중복.

해결. 정식 **브리핑 카테고리**(SKILL.md + launchd)로 옮긴다. 아침·저녁은 서로 다른 *의도된* 실행이므로 중복 버그가 구조적으로 사라진다. 메일은 어떤 경로로도 보내지 않는다(사용자 요청).

## 목표

- 네이버(035420) 주가 중심 브리핑 카테고리를 만든다.
- 평일(월~금) 08:00·18:00 2회, 주말 08:00 1회 포털에 발행한다.
- 메일 발송 없음. 포털 피드에만 노출.
- 같은 날 아침/저녁 2건이 제목으로 구분된다(`[프리뷰]` / `[마감]`).

## 비목표

- 메일 발송, 구독자 시드.
- 커스텀 주제 시스템 수정(별개 — 중복 버그는 이 작업으로 우회되며, 커스텀 주제 자체 버그 수정은 후속).
- 18:00 외 추가 실행 시각, 장중 실시간 갱신.

## 아키텍처

기존 멀티 카테고리 브리핑 시스템(`services/brief/`)을 그대로 활용한다.

- 카테고리 = `categories/{slug}/SKILL.md`. `list_categories()`가 `enabled: true`를 스캔.
- launchd `com.popory.brief`가 매일 08:00 `run_daily.sh` 호출 → 전 카테고리 generate·publish.
- 발행 = `publish_to_portal.py` → `POST /api/published_items` → `/p/brief-{slug}/` 노출.

추가/변경은 다음 6개.

### 1. 새 delivery_mode `portal_only`

`services/brief/popory_brief/categories.py`의 `VALID_MODES`에 `"portal_only"` 추가.

```python
VALID_MODES = {"standalone", "bundled", "portal_only"}
```

`run_daily.sh`는 카테고리를 `MODE == "standalone"`이면 `STANDALONE_SLUGS`, `"bundled"`이면 `BUNDLED_SLUGS`에 넣어 메일 발송한다. `portal_only`는 어느 배열에도 안 들어가므로 **publish는 되고 메일은 자동 제외**된다(publish 단계는 모드와 무관하게 실행됨). run_daily.sh의 메일 로직 변경 불필요.

### 2. 카테고리 `categories/naver-stock/SKILL.md`

frontmatter.

```yaml
slug: naver-stock
name: 네이버 주식
delivery_mode: portal_only
subject_template: "[{name} 브리핑] {date}"
sender_name: "네이버 주식 브리핑"
enabled: true
description: "네이버(035420) 주가·수급·증권사 리포트·공시 데일리 브리핑"
```

본문(system prompt) 핵심.

- 대상. 네이버 주식회사(035420) 주가·거래량·외국인/기관 수급·증권사 목표주가·리포트·공시·실적·주가에 영향 주는 사업/규제 이슈.
- **시각 분기**. user_msg로 전달되는 현재 시각(KST)을 확인.
  - 장 시작 전(대략 ~09:00, 오전 실행)이면 `[프리뷰]` — 간밤 미국 증시·환율·반도체/빅테크 동향, 개장 전 체크포인트, 예정된 공시·이벤트.
  - 장 마감 후(오후 실행)이면 `[마감]` — 당일 종가·등락률·거래량·수급(외국인·기관 순매수/도), 당일 주요 뉴스 마감 랩.
- 수집 윈도우. 주식 특성상 "직전 거래일~당일". 법률 카테고리의 [D-2, D]와 다름을 명시.
- 출력 계약. 기존과 동일 — `<body_markdown>` + `<meta_json>{title, summary, tags, published_at}`. title은 `[네이버 주식][프리뷰] {date}` / `[네이버 주식][마감] {date}` 형태로 세션 표기.
- 형식 정책. H1 없음, 불릿 `-`, 이모지·§ 금지, 출처 라인 `[매체 — 제목 (YYYY.M.D)](URL)`.

### 3. `run_daily.sh` — `--only <slug>` 플래그

- 인자 파싱에 `--only) ONLY_SLUG="$2"; shift ;;` 추가(또는 `--only=<slug>` 형태). 기본 빈 값.
- 카테고리 스캔 결과 `CATEGORIES`를 `ONLY_SLUG`가 있으면 해당 slug 한 줄로 필터.
- `ONLY_SLUG`가 있으면 커스텀 주제 블록(섹션 4) 전체 skip.
- `--no-email`은 추가하지 않음(portal_only가 메일 제외를 담당).

### 4. `generate_brief.py` — 현재 시각 주입

user_msg를 날짜만에서 시각 포함으로.

```python
now_str = date_obj.strftime("%Y-%m-%d %H:%M")  # date_obj는 --date 미지정 시 now(KST)
user_msg = (
    f"지금은 {now_str} (KST)입니다. 시스템 매뉴얼의 절차를 따라 ... 작성하세요. ..."
)
```

`date_str`·`published_at`·파일명 로직은 불변. 타 카테고리는 "지금은 …" 문구만 바뀌고 동작 영향 없음.

### 5. 저녁 launchd 잡 `com.popory.brief-naver-stock-pm.plist`

`~/Library/LaunchAgents/`에 설치.

- `ProgramArguments`. `/bin/bash run_daily.sh --only naver-stock --now`.
- `StartCalendarInterval`. 배열로 Weekday 1~5(월~금) × Hour 18, Minute 0.
- `--now`로 지터 없이 즉시 실행(저녁은 18:00에 가깝게).
- 로그·환경변수·WorkingDirectory는 기존 `com.popory.brief.plist`와 동일.

### 6. prod D1 정리

- `DELETE FROM user_brief_topics WHERE id='8a2c3d67b4f1'`.
- `DELETE FROM area_subscriptions WHERE area='custom-8a2c3d67b4f1'`.
- `DELETE FROM published_items WHERE area IN ('custom-8a2c3d67b4f1','custom-c55a789f4e5e')`.

## 데이터 흐름

```
[평일 08:00] com.popory.brief → run_daily.sh (전 카테고리)
  → naver-stock generate(프리뷰) → publish brief-naver-stock → 포털
  → portal_only이므로 메일 skip

[평일 18:00] com.popory.brief-naver-stock-pm → run_daily.sh --only naver-stock --now
  → naver-stock generate(마감) → publish brief-naver-stock → 포털

[주말 08:00] com.popory.brief → naver-stock generate(프리뷰) → publish → 포털
  (저녁 잡은 Weekday 1~5라 주말 미실행)
```

## 검증

1. `python -c "from popory_brief.categories import load_category; print(load_category('naver-stock').delivery_mode)"` → `portal_only`.
2. `run_daily.sh --dry-run --only naver-stock` → naver-stock만 generate(DRY publish), 메일 로그 없음, 정상 종료.
3. 저녁 plist `launchctl load` 후 `--only naver-stock --now` 1회 수동 실행 → 포털 `/p/brief-naver-stock/`에 발행물 확인, 메일 미발송 확인.
4. prod 정리 후 `published_items`에 custom-* 잔존 0건.
5. 기존 카테고리 회귀. 6개 카테고리 정상 generate(타 카테고리 user_msg 변경 무해 확인).

## 리스크·주의

- **장중/마감 시각 판단**. 모델이 user_msg의 시각으로 프리뷰/마감을 분기. 18:00은 장 마감(15:30) 후라 `[마감]`, 08:00은 개장 전이라 `[프리뷰]`로 안정적.
- **주식 정보 정확도**. 종가·등락률은 WebSearch 의존. 실시간 시세 API 미사용이라 마감 직후 수치는 지연·근사일 수 있음 → SKILL.md에 "확인된 종가/공식 수치 우선, 미확정이면 명시" 지시.
- **published_at**. 카테고리 경로는 `published_at = 자정(date_obj) timestamp`로 결정적이라 피드 정렬 안정적(커스텀 주제의 모델 출력 의존 문제 없음). 단 같은 날 프리뷰·마감 2건이 같은 published_at(자정)을 가져 정렬 동률 가능 → 피드는 그대로 2건 노출되며 title로 구분.
- **Claude Max 사용량 윈도우**. 저녁 18:00 단일 카테고리 생성이 5시간 롤링 윈도우를 사용자 사용과 공유. 1개 카테고리라 부담은 작음.
