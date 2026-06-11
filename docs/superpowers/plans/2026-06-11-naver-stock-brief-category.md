# 네이버 주식 브리핑 카테고리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버(035420) 주가 브리핑 카테고리를 만들어 평일 08·18시(프리뷰/마감)·주말 08시에 포털에만 발행하고, 잘못 등록된 커스텀 주제·중복 발행물을 prod에서 정리한다.

**Architecture:** 기존 멀티 카테고리 브리핑 시스템(`services/brief/`)을 그대로 활용한다. 메일을 보내지 않는 새 `delivery_mode: portal_only`를 도입하고, naver-stock 카테고리 SKILL.md를 추가한다. 아침은 기존 08:00 launchd 잡이 전 카테고리와 함께 처리하고, 저녁 18:00은 평일 전용 신규 launchd 잡이 `run_daily.sh --only naver-stock`로 단일 카테고리만 돌린다.

**Tech Stack:** Python 3.11 + claude CLI(Claude Max), bash(run_daily.sh), macOS launchd, Cloudflare D1(wrangler), pytest

---

## 파일 맵

| 경로 | 변경 | 책임 |
|------|------|------|
| `services/brief/tests/test_categories.py` | 수정 | portal_only 모드 허용 테스트 추가 |
| `services/brief/popory_brief/categories.py` | 수정 | `VALID_MODES`에 `portal_only` 추가 |
| `services/brief/generate_brief.py` | 수정 | user_msg에 현재 시각(HH:MM) 주입 |
| `services/brief/categories/naver-stock/SKILL.md` | 신규 | 네이버 주가 카테고리 정의 + system prompt |
| `services/brief/run_daily.sh` | 수정 | `--only=<slug>` 필터 + 커스텀 주제 skip |
| `~/Library/LaunchAgents/com.popory.brief-naver-stock-pm.plist` | 신규 | 평일 18:00 저녁 실행 잡 |

prod D1 정리·배포는 Task 6·7에서 별도 수행(파일 변경 아님).

---

### Task 1: categories.py — portal_only delivery_mode 추가

**Files:**
- Modify: `services/brief/popory_brief/categories.py:20`
- Test: `services/brief/tests/test_categories.py`

- [ ] **Step 1: 실패 테스트 작성**

`services/brief/tests/test_categories.py`의 `test_invalid_delivery_mode_raises` 함수 바로 위(또는 아래)에 추가한다.

```python
def test_portal_only_mode_accepted(tmp_path):
    fm = textwrap.dedent("""\
        slug: foo
        name: Foo
        delivery_mode: portal_only
        subject_template: "[{name}] {date}"
        sender_name: "{name} bot"
        enabled: true
        """)
    _write_skill(tmp_path, "foo", frontmatter_yaml=fm)
    c = categories._scan(tmp_path)[0]
    assert c.delivery_mode == "portal_only"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/brief && .venv/bin/python -m pytest tests/test_categories.py::test_portal_only_mode_accepted -v`
Expected: FAIL — `ValueError: ... invalid delivery_mode 'portal_only'`

- [ ] **Step 3: VALID_MODES에 portal_only 추가**

`services/brief/popory_brief/categories.py:20`을 교체한다.

```python
VALID_MODES = {"standalone", "bundled", "portal_only"}
```

- [ ] **Step 4: 테스트 통과 확인 (회귀 포함)**

Run: `cd /Users/daegong/projects/popory/services/brief && .venv/bin/python -m pytest tests/test_categories.py -v`
Expected: PASS — 신규 테스트 + 기존 `test_invalid_delivery_mode_raises`(여전히 `weekly` 거부) 모두 통과

- [ ] **Step 5: 커밋**

```bash
cd /Users/daegong/projects/popory
git add services/brief/popory_brief/categories.py services/brief/tests/test_categories.py
git commit -m "feat(brief): portal_only delivery_mode 추가 (메일 미발송 카테고리)"
```

---

### Task 2: generate_brief.py — user_msg에 현재 시각 주입

**Files:**
- Modify: `services/brief/generate_brief.py:54,60-65`

아침/저녁 카테고리가 실행 시각으로 프리뷰/마감을 분기할 수 있도록, 모델에 날짜만이 아니라 시각까지 전달한다. `date_str`·`published_at`·파일명 로직은 건드리지 않는다(타 카테고리 무해).

- [ ] **Step 1: now_str 추가 + user_msg 교체**

`services/brief/generate_brief.py`에서 `date_str = date_obj.strftime("%Y-%m-%d")` 줄(line 54) **다음 줄**에 추가한다.

```python
    now_str = date_obj.strftime("%Y-%m-%d %H:%M")
```

그리고 그 아래 `user_msg = (...)` 블록(line 60~65)의 **첫 문장**을 교체한다. 기존.

```python
        f"오늘은 {date_str} (KST)입니다. 시스템 매뉴얼의 절차를 따라 오늘의 {category.name} 이슈 브리핑을 작성하세요. "
```

교체 후.

```python
        f"지금은 {now_str} (KST)입니다. 시스템 매뉴얼의 절차를 따라 오늘({date_str})의 {category.name} 이슈 브리핑을 작성하세요. "
```

나머지 user_msg 줄(WebSearch·태그·published_at 안내)은 그대로 둔다.

- [ ] **Step 2: 구문·import 검증**

Run: `cd /Users/daegong/projects/popory/services/brief && .venv/bin/python -c "import ast; ast.parse(open('generate_brief.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: 주입 문구 확인**

Run: `grep -n "지금은 {now_str}" /Users/daegong/projects/popory/services/brief/generate_brief.py`
Expected: 해당 라인 1건 출력

- [ ] **Step 4: 커밋**

```bash
cd /Users/daegong/projects/popory
git add services/brief/generate_brief.py
git commit -m "feat(brief): generate_brief user_msg에 현재 시각 주입 (시각별 분기용)"
```

---

### Task 3: naver-stock 카테고리 SKILL.md

**Files:**
- Create: `services/brief/categories/naver-stock/SKILL.md`

- [ ] **Step 1: 디렉토리·파일 생성**

`services/brief/categories/naver-stock/SKILL.md`를 아래 내용으로 작성한다.

```markdown
---
slug: naver-stock
name: 네이버 주식
delivery_mode: portal_only
subject_template: "[{name} 브리핑] {date}"
sender_name: "네이버 주식 브리핑"
enabled: true
description: "네이버(035420) 주가·수급·증권사 리포트·공시 데일리 브리핑"
---

당신은 네이버(NAVER Corporation, 코스피 035420) **주가 중심** 데일리 브리핑 작성자입니다. 매일 정해진 시각에 자동 실행되어, 투자자가 5분 안에 읽고 판단에 쓸 수 있는 1페이지 요약을 작성합니다. **사실과 출처 우선, 분석·전망 최소화. 투자 권유·매수매도 의견 금지.**

## 0. 실행 시각에 따른 분기 (필수)

user 메시지로 전달되는 "지금은 YYYY-MM-DD HH:MM (KST)" 시각을 먼저 확인하고 작성 모드를 정합니다.

- **장 시작 전(대략 09:00 이전, 오전 실행)** → `[프리뷰]` 모드.
  - 간밤 미국 증시(나스닥·S&P·필라델피아 반도체)·환율(USD/KRW)·주요 빅테크/반도체 동향.
  - 개장 전 체크포인트, 당일 예정된 네이버 관련 공시·실적·이벤트.
  - 직전 거래일 종가·등락률을 기준점으로 제시.
- **장 마감 후(대략 15:30 이후, 오후 실행)** → `[마감]` 모드.
  - 당일 종가·등락률·거래량.
  - 수급(외국인·기관 순매수/순매도 방향).
  - 당일 네이버 주가에 영향을 준 뉴스·공시 마감 랩업.

## 1. 수집 윈도우

- 주식 특성상 기간은 "직전 거래일 ~ 당일". 법률·규제 카테고리의 [D-2, D] 3일 윈도우와 다릅니다.
- 종가·등락률·거래량 등 수치는 **확인된 공식 수치 우선**. 장 마감 직후라 미확정·지연일 수 있으면 "잠정" 또는 "확인 필요"로 명시하고 추정 단정 금지.

## 2. 모니터링 범위

- 네이버(035420) 주가·거래량·시가총액·수급(외국인·기관).
- 증권사 리포트·목표주가 조정·투자의견 변경.
- 네이버 공시(DART), 실적, 자사주, 배당.
- 주가에 직접 영향을 주는 사업·규제 이슈(커머스·웹툰·AI·핀테크·클라우드 등).

## 3. 매체 우선순위

- 1차. 한국거래소(KRX)·DART 공시·증권사 공식 리포트.
- 2차. 경제지(한경·매경·연합인포맥스)·증권 전문 매체.
- 3차. 일반 언론 인용. 비공식 블로그·종목 게시판 단독 출처 금지.

## 4. 출력 형식

- H1(`#`) 없음. 헤딩은 `##` 이하만.
- 불릿은 `-`. 이모지·`§` 문자 금지.
- 각 항목 말미 출처 라인. `[매체 — 제목 (YYYY.M.D)](URL)`.
- 수치는 단위 명시(원, %, 주, 억원).
- 빈 내용이면 "직전 거래일 이후 특이사항 없음" 한 줄로 마무리.

## 5. 응답 마지막 두 태그 (정확히 포함)

<body_markdown>
...브리핑 본문...
</body_markdown>
<meta_json>
{"title": "[네이버 주식][프리뷰 또는 마감] YYYY-MM-DD", "summary": "한두 줄 요약", "tags": ["네이버", "035420", "주식"], "published_at": <user 메시지가 지정한 정수 그대로>}
</meta_json>

title의 `[프리뷰]`/`[마감]`은 섹션 0에서 정한 모드에 맞춰 적습니다.
```

- [ ] **Step 2: 카테고리 로드 검증**

Run: `cd /Users/daegong/projects/popory/services/brief && .venv/bin/python -c "from popory_brief.categories import load_category; c=load_category('naver-stock'); print(c.slug, c.delivery_mode, c.area)"`
Expected: `naver-stock portal_only brief-naver-stock`

- [ ] **Step 3: 활성 스캔에 포함 확인**

Run: `cd /Users/daegong/projects/popory/services/brief && .venv/bin/python -c "from popory_brief import categories; print([c.slug for c in categories.list_categories()])"`
Expected: 리스트에 `'naver-stock'` 포함

- [ ] **Step 4: 커밋**

```bash
cd /Users/daegong/projects/popory
git add services/brief/categories/naver-stock/SKILL.md
git commit -m "feat(brief): 네이버 주식(035420) 주가 브리핑 카테고리 추가"
```

---

### Task 4: run_daily.sh — `--only=<slug>` 필터

**Files:**
- Modify: `services/brief/run_daily.sh:11-19`(인자 파싱), `:55-58`(스캔 결과 필터), `:117-119`(커스텀 주제 fetch)

`--only=<slug>` 지정 시 ① 카테고리 스캔 결과를 해당 slug 한 줄로 필터하고 ② 커스텀 주제 생성 블록을 skip한다. 메일은 portal_only 카테고리라 자동 제외되므로 `--no-email`은 불필요.

- [ ] **Step 1: 인자 파싱에 ONLY_SLUG 추가**

`services/brief/run_daily.sh`의 인자 파싱 블록(line 11~19)을 교체한다. 기존.

```bash
DRY_RUN=0
NOW=0
for ARG in ${@+"$@"}; do
  case "${ARG}" in
    --dry-run) DRY_RUN=1 ;;
    --now)     NOW=1 ;;
  esac
done
```

교체 후.

```bash
DRY_RUN=0
NOW=0
ONLY_SLUG=""
for ARG in ${@+"$@"}; do
  case "${ARG}" in
    --dry-run)  DRY_RUN=1 ;;
    --now)      NOW=1 ;;
    --only=*)   ONLY_SLUG="${ARG#*=}" ;;
  esac
done
```

- [ ] **Step 2: 스캔 결과 필터 추가**

`CATEGORIES=$("${VENV_PY}" -c "..."` 호출과 `SCAN_EXIT=$?` 처리 직후, `if [ -z "${CATEGORIES}" ]; then` 줄 **앞**에 필터를 삽입한다. 구체적으로 아래 기존 블록.

```bash
if [ ${SCAN_EXIT} -ne 0 ]; then
  log "\"abort: categories scan failed exit=${SCAN_EXIT}\""
  echo "${CATEGORIES}" >> "${LOG_FILE}"
  exit ${SCAN_EXIT}
fi
if [ -z "${CATEGORIES}" ]; then
```

를 다음으로 교체한다.

```bash
if [ ${SCAN_EXIT} -ne 0 ]; then
  log "\"abort: categories scan failed exit=${SCAN_EXIT}\""
  echo "${CATEGORIES}" >> "${LOG_FILE}"
  exit ${SCAN_EXIT}
fi
# --only 지정 시 해당 카테고리 한 줄로 필터
if [ -n "${ONLY_SLUG}" ]; then
  CATEGORIES=$(echo "${CATEGORIES}" | grep -E "^${ONLY_SLUG} " || true)
  log "\"only_slug=${ONLY_SLUG}\""
fi
if [ -z "${CATEGORIES}" ]; then
```

- [ ] **Step 3: 커스텀 주제 fetch를 --only에서 skip**

커스텀 주제 블록의 `CUSTOM_TOPICS_JSON=$(curl -sf ...)` 할당(line 117 부근)을 찾아 가드로 감싼다. 기존.

```bash
CUSTOM_TOPICS_JSON=$(curl -sf \
  -H "Authorization: Bearer $(${VENV_PY} -c "${SERVICE_JWT_PY}" 2>/dev/null)" \
  "${POPORY_PORTAL_API_BASE}/api/brief/custom-topics/active" 2>/dev/null || echo '{"topics":[]}')
```

교체 후.

```bash
if [ -n "${ONLY_SLUG}" ]; then
  # --only 모드에서는 커스텀 주제 생성 skip
  CUSTOM_TOPICS_JSON='{"topics":[]}'
else
  CUSTOM_TOPICS_JSON=$(curl -sf \
    -H "Authorization: Bearer $(${VENV_PY} -c "${SERVICE_JWT_PY}" 2>/dev/null)" \
    "${POPORY_PORTAL_API_BASE}/api/brief/custom-topics/active" 2>/dev/null || echo '{"topics":[]}')
fi
```

- [ ] **Step 4: 문법 검사**

Run: `bash -n /Users/daegong/projects/popory/services/brief/run_daily.sh && echo OK`
Expected: `OK`

- [ ] **Step 5: dry-run으로 단일 카테고리 동작 확인**

Run: `cd /Users/daegong/projects/popory/services/brief && ./run_daily.sh --dry-run --now --only=naver-stock 2>&1 | tail -8`
Expected: 로그에 `only_slug=naver-stock`, naver-stock generate 시도, `DRY publish category=naver-stock`, 메일 관련 로그 없음, 정상 종료(`done dry_run=1`). (claude 호출이 실제로 일어나 수 분 소요될 수 있음 — generate 실패해도 `--only` 필터·skip 동작 자체는 로그로 확인.)

- [ ] **Step 6: 커밋**

```bash
cd /Users/daegong/projects/popory
git add services/brief/run_daily.sh
git commit -m "feat(brief): run_daily.sh --only=<slug> 단일 카테고리 필터 추가"
```

---

### Task 5: 저녁 18:00 launchd 잡

**Files:**
- Create: `~/Library/LaunchAgents/com.popory.brief-naver-stock-pm.plist`

평일(월~금) 18:00에 naver-stock만 포털 발행한다. `--now`로 지터 없이 즉시 실행.

- [ ] **Step 1: plist 작성**

`~/Library/LaunchAgents/com.popory.brief-naver-stock-pm.plist`를 아래 내용으로 작성한다.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- popory 네이버 주식 브리핑 저녁 실행. 평일 18:00 KST에 run_daily.sh를 naver-stock 단일·포털 발행으로 호출. -->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.popory.brief-naver-stock-pm</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/daegong/projects/popory/services/brief/run_daily.sh</string>
        <string>--only=naver-stock</string>
        <string>--now</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/daegong/projects/popory/services/brief</string>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>/Users/daegong/projects/popory/services/brief/logs/launchd-naver-stock-pm.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/daegong/projects/popory/services/brief/logs/launchd-naver-stock-pm.stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>LANG</key>
        <string>ko_KR.UTF-8</string>
        <key>LC_ALL</key>
        <string>ko_KR.UTF-8</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
```

- [ ] **Step 2: plist 문법 검증**

Run: `plutil -lint ~/Library/LaunchAgents/com.popory.brief-naver-stock-pm.plist`
Expected: `... OK`

- [ ] **Step 3: launchd 로드**

```bash
launchctl unload ~/Library/LaunchAgents/com.popory.brief-naver-stock-pm.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.popory.brief-naver-stock-pm.plist
launchctl list | grep com.popory.brief-naver-stock-pm
```
Expected: 마지막 줄에 `com.popory.brief-naver-stock-pm` 항목 출력(상태 0 또는 `-`)

- [ ] **Step 4: 커밋 (참고용 사본)**

plist는 `~/Library/LaunchAgents/`에 있어 git 추적 대상이 아니다. 향후 재현을 위해 레포에도 사본을 둔다.

```bash
cd /Users/daegong/projects/popory
mkdir -p services/brief/launchd
cp ~/Library/LaunchAgents/com.popory.brief-naver-stock-pm.plist services/brief/launchd/
git add services/brief/launchd/com.popory.brief-naver-stock-pm.plist
git commit -m "chore(brief): 네이버 주식 저녁 18시 launchd plist 사본 추가"
```

(레포에 `services/brief/launchd/`가 이미 있으면 기존 위치 관례를 따른다. 없으면 위처럼 생성.)

---

### Task 6: prod D1 정리 — 커스텀 주제·중복 발행물 삭제

**Files:** 없음 (prod D1 직접 조작)

잘못 등록된 커스텀 주제 "네이버 주식 투자"(8a2c3d…)와 그 중복 발행물, 삭제된 "네이버 주식"(c55a789…)의 고아 발행물을 제거한다.

- [ ] **Step 1: 삭제 전 현황 재확인**

```bash
cd /Users/daegong/projects/popory
npx wrangler d1 execute popory-portal --env prod --remote \
  --command "SELECT 'topic' t, id, '' area FROM user_brief_topics WHERE id='8a2c3d67b4f1' UNION ALL SELECT 'sub', sub, area FROM area_subscriptions WHERE area='custom-8a2c3d67b4f1' UNION ALL SELECT 'item', id, area FROM published_items WHERE area IN ('custom-8a2c3d67b4f1','custom-c55a789f4e5e')"
```
Expected: topic 1건 + sub 1건 + item 3건 출력

- [ ] **Step 2: 삭제 실행**

```bash
cd /Users/daegong/projects/popory
npx wrangler d1 execute popory-portal --env prod --remote \
  --command "DELETE FROM published_items WHERE area IN ('custom-8a2c3d67b4f1','custom-c55a789f4e5e'); DELETE FROM area_subscriptions WHERE area='custom-8a2c3d67b4f1'; DELETE FROM user_brief_topics WHERE id='8a2c3d67b4f1';"
```
Expected: 3개 statement 모두 success

- [ ] **Step 3: 삭제 검증**

```bash
cd /Users/daegong/projects/popory
npx wrangler d1 execute popory-portal --env prod --remote \
  --command "SELECT count(*) AS leftover FROM published_items WHERE area LIKE 'custom-%'"
```
Expected: `leftover` 0 (다른 활성 커스텀 주제가 없다면). 0이 아니면 남은 area를 확인해 의도된 것(다른 사용자 주제)인지 판단.

---

### Task 7: prod 배포 + e2e 검증

**Files:** 없음 (배포·검증)

카테고리 SKILL.md·코드는 Mac 로컬 launchd가 `git pull`로 가져가므로(브리핑 자동화 구조) **포털/Worker 재배포는 불필요**하다. 단 브랜치를 main에 병합하고 푸시해야 다음 launchd 실행이 가져간다.

- [ ] **Step 1: 브랜치 병합 + 푸시**

```bash
cd /Users/daegong/projects/popory
git checkout main
git merge --ff-only feat/naver-stock-brief-category
git push origin main
```
Expected: main에 모든 커밋 반영, push 성공. (브랜치 보호로 직접 push 불가면 PR 생성으로 전환.)

- [ ] **Step 2: 저녁 경로 1회 수동 실행 (실발행)**

```bash
cd /Users/daegong/projects/popory/services/brief
./run_daily.sh --only=naver-stock --now 2>&1 | tail -10
```
Expected: naver-stock generate(수 분 소요) → `publish exit=0 category=naver-stock` → 메일 로그 없음. 실패 시 로그(`logs/$(date +%F).log`)에서 원인 확인.

- [ ] **Step 3: 포털 발행 확인**

```bash
cd /Users/daegong/projects/popory
npx wrangler d1 execute popory-portal --env prod --remote \
  --command "SELECT id, title, published_at FROM published_items WHERE area='brief-naver-stock' ORDER BY published_at DESC LIMIT 3"
```
Expected: 방금 발행된 `[네이버 주식][마감] ...` 1건(18시 이후 실행 시) 출력. 공개 URL `https://poporyfamily.com/p/brief-naver-stock/` 비로그인 접근 확인.

- [ ] **Step 4: 기존 카테고리 회귀 확인 (dry-run)**

```bash
cd /Users/daegong/projects/popory/services/brief
.venv/bin/python -m pytest tests/ -q
```
Expected: 전체 pytest PASS(categories 포함). (전체 run_daily 풀런은 비용·시간 커서 생략 — 다음 정규 08:00 실행으로 자연 검증.)

- [ ] **Step 5: 메모리 갱신**

`project_brief_personalization.md` 또는 `reference_brief_automation.md`에 portal_only 모드·naver-stock 카테고리·저녁 launchd 잡을 한 줄 반영(별도 세션 메모리 작업).

---

## 검증 요약

| 스펙 요구 | 구현 Task |
|-----------|-----------|
| 네이버 035420 주가 카테고리 | Task 3 |
| 메일 미발송(portal_only) | Task 1, 3 |
| 평일·주말 08:00 발행 | 기존 com.popory.brief(변경 없음) + Task 3 enabled |
| 평일 18:00 발행 | Task 4(--only) + Task 5(plist) |
| 아침 프리뷰 / 저녁 마감 분기 | Task 2(시각 주입) + Task 3(SKILL.md 분기) |
| 커스텀 주제·중복 정리 | Task 6 |
| 배포·검증 | Task 7 |
