# claude CLI 에 줄 YouTube 영상 대본 system/user 프롬프트. 장면 배열 + 메타를 출력시킨다.
from typing import Any

# 채널 식별자·브랜딩. 구독 링크는 LLM이 지어내면 깨지므로 파싱 단계에서 결정적으로 append 한다.
CHANNEL_ID = "UCMbHbpCaIONuzHqklo_grTA"
CHANNEL_SUB_URL = f"https://www.youtube.com/channel/{CHANNEL_ID}?sub_confirmation=1"
BRAND_LINE = "포포리 책방 — 한 권의 책에서 길어올린 인생의 지혜."
# 구독 유도 + 링크(브랜드 줄 없음). 내레이션엔 CTA를 넣지 않는다(브랜딩 유지).
SUBSCRIBE_CTA = (
    "매일 한 권의 책에서 길어올린 인생의 지혜를 전합니다. 구독하시면 다음 이야기를 놓치지 않아요.\n"
    f"▶ 구독 {CHANNEL_SUB_URL}"
)
# 신규 영상용(요약만 생성되므로 브랜드 줄까지 포함해 붙인다).
DESCRIPTION_CTA = f"{SUBSCRIBE_CTA}\n{BRAND_LINE}"


# 엔딩 CTA 장면(롱폼 전용). LLM 이 마지막 장면에 CTA 를 빠뜨리면 video_contract.ensure_ending_cta 가
# 이 장면을 결정적으로 덧붙인다. 2026-09 시청 지속·구독 전환을 위해 도입 — 예전엔 내레이션 CTA 가
# 전면 금지였다(쇼츠는 지금도 금지).
ENDING_CTA_CAPTION = "함께 보면 좋은 영상"
ENDING_CTA_NARRATION = (
    "오늘 이야기가 도움이 되셨다면 구독과 좋아요 부탁드립니다. "
    "여러분은 이 책의 메시지 중 어떤 부분이 가장 마음에 남으셨나요? 댓글로 자유롭게 남겨주세요. "
    "또 다른 책의 통찰이 궁금하시다면, 화면에 보이는 추천 영상도 함께 감상해 보시길 권합니다."
)
ENDING_CTA_IMAGE_PROMPT = (
    "warm cozy reading nook at dusk, an open book on a wooden table beside a glowing lamp, "
    "soft bokeh bookshelf in the background, no people, photorealistic, cinematic"
)


def ending_cta_scene() -> dict[str, str]:
    """엔딩 CTA 폴백 장면(복사본 — 호출자가 수정해도 상수가 오염되지 않게)."""
    return {"caption": ENDING_CTA_CAPTION, "narration": ENDING_CTA_NARRATION,
            "image_prompt": ENDING_CTA_IMAGE_PROMPT}


def append_description_cta(description: str) -> str:
    """신규 영상 설명란(요약) 뒤에 구독 CTA+브랜딩을 붙인다(멱등 — 링크 있으면 그대로)."""
    desc = (description or "").rstrip()
    if CHANNEL_SUB_URL in desc:
        return desc
    return f"{desc}\n\n{DESCRIPTION_CTA}" if desc else DESCRIPTION_CTA


def append_subscribe_cta(description: str) -> str:
    """기존 영상 소급용 — 구독 CTA만 붙인다(브랜드 줄은 이미 있으므로 중복 안 시킴). 멱등."""
    desc = (description or "").rstrip()
    if CHANNEL_SUB_URL in desc:
        return desc
    return f"{desc}\n\n{SUBSCRIBE_CTA}" if desc else SUBSCRIBE_CTA


def _rules(scene_count: int, image_style_kw: str) -> str:
    return f"""당신은 한국어 YouTube 영상 대본 작가입니다. 주제로 슬라이드쇼형 영상의 대본을 만듭니다.

## 1. 리서치
- WebSearch·WebFetch 로 주제 관련 신뢰할 자료를 수집합니다.
- 사용자가 제공한 참고 링크가 있으면 반영합니다.
- 확인된 사실만 씁니다.

## 2. 구성
- 영상은 장면(scene) 약 {scene_count}개로 구성합니다.
- 각 장면은 caption(화면에 크게 띄울 짧은 헤드라인, 16자 이내 핵심 단어 위주)과 narration(그 장면에서 읽어줄 내레이션)으로 이뤄집니다.
- **각 장면의 narration은 소리 내어 읽었을 때 약 35초 분량(보통 5~7문장)으로 충분히 풀어서** 씁니다. 한 장면이 ~35초이고 장면이 {scene_count}개이므로 영상은 대략 {scene_count}×35초가 됩니다. narration이 짧으면 영상이 설정 길이보다 짧아지니, 각 장면을 구체적 사례·설명·맥락으로 충분히 채웁니다.
- 각 장면에 image_prompt(그 장면을 묘사하는 영어 이미지 생성 프롬프트, 한 문장. {image_style_kw} 스타일이며 이미지 안에 글자/텍스트는 넣지 않습니다)도 포함합니다.
- 모든 장면의 image_prompt는 색감·조명·분위기를 일관되게 유지해 한 영상처럼 보이게 합니다(같은 {image_style_kw} 톤 유지).
- image_prompt는 자연스러운 실사 장면을 묘사합니다. **사람 얼굴은 되도록 넣지 않습니다** — 이미지 생성 모델이 얼굴·눈·손을 기형으로 만드는 일이 잦아 배경으로 못 쓰게 됩니다. 사람이 꼭 필요하면 **뒷모습·실루엣·원경**으로 담아 이목구비가 드러나지 않게 하고, 그것도 어려우면 사람 대신 **사물·풍경·정물**(책·창문·길·불빛·의자)로 장면을 표현합니다. **정면 얼굴 클로즈업과 손 클로즈업은 금지**이고, **팔짱·턱 괴기처럼 팔이 몸 앞에서 접히거나 교차하고 손이 얼굴·몸에 닿는 포즈도 금지**입니다 — 생성 모델이 팔 개수와 어깨→손 연결을 잃는 구도입니다. 사람이 나오면 팔은 자연스럽게 내리거나 벌린 자세로 둡니다.
- 흐름은 **프리후크(첫 장면) → 본문 → 여운 있는 정리 → 엔딩 CTA(마지막 장면)** 입니다.
- **첫 장면은 프리후크입니다(시청자의 30~50%가 첫 15초에 이탈 여부를 정합니다).** 서정적인 배경 설명으로 시작하지 말고, **첫 문장에 가장 충격적인 결론이나 극적인 대비를 먼저 던집니다**(예: "100억을 남기고 떠난 청소부, 그리고 파산한 하버드 출신 금융 임원. 두 사람의 운명을 가른 건 학벌도 지식도 아니었습니다."). 첫 장면 끝에는 "오늘 영상에서는 …을 정리해 드립니다"처럼 이 영상이 무엇을 줄지 한 문장으로 예고합니다. 이야기의 도입부(인물·배경)는 두 번째 장면부터 풉니다.
- **중간중간 시청자에게 직접 질문을 던지고**, **3~4장면마다(약 2~3분) 지금까지의 내용을 한 문장으로 정리하는 요약 문장**을 넣습니다(예: "여기까지 정리하면, 부를 지키는 건 수익률이 아니라 태도였습니다.").
- **마지막 장면은 엔딩 CTA 장면입니다.** caption 은 "함께 보면 좋은 영상" 같은 마무리 헤드라인으로 두고, narration 은 다음 세 단계를 자연스럽게 잇습니다. ① "오늘 이야기가 도움되셨다면 구독과 좋아요 부탁드립니다." ② 영상 주제와 이어지는 질문 하나를 던지고 "댓글로 자유롭게 남겨주세요."라고 청합니다. ③ "또 다른 통찰을 원하신다면 화면에 보이는 추천 영상도 함께 감상해 보세요."로 다음 시청을 권합니다. **채널의 다른 영상 제목을 지어내지 마세요** — 추천 영상은 "화면에 보이는 추천 영상"이라고만 말합니다(종료 화면은 업로드 후 붙습니다). 구독·좋아요 요청은 **이 마지막 장면에만** 넣고, 본문 장면의 내레이션에는 넣지 않습니다.
- **카드 장면(그래픽 카드) 2~3개.** 유화·실사 일러스트만 10분 내내 반복되면 지루하므로, 1~2분마다 한 번씩(장면 4~5개마다 하나) 장면에 `card` 를 붙입니다. 그 장면이 시작되기 전에 어두운 배경에 큰 글씨로 카드가 3~4초 뜹니다. 두 종류가 있습니다.
  - 명언 카드 `{{"type": "quote", "text": "책 속 핵심 문장 (40자 이내)", "source": "책제목 또는 저자"}}` — 리서치로 **확인된 문장만** 인용합니다. 확인 안 되면 저자에게 귀속하지 말고 source 를 비우고 책의 핵심 메시지를 한 문장으로 씁니다.
  - 핵심 요약 카드 `{{"type": "keypoints", "title": "부자의 3가지 원칙", "items": ["복리", "인내심", "통제권"]}}` — items 는 2~4개, 각 12자 이내.
  - 카드가 없는 장면은 `card` 키를 아예 넣지 않습니다. 첫 장면과 마지막 장면엔 붙이지 않습니다.
- 자연스러운 한국어 구어체. 문장은 마침표나 물음표로 끝냅니다(콜론 종결 금지). **'음·어·아·그' 같은 의미 없는 간투사·추임새는 쓰지 않습니다.**
- **문장 끝(어미)을 다양하게 씁니다** — 내레이션은 문장별로 음성 합성되므로 같은 어미가 이어지면 모든 문장이 똑같은 억양으로 끝나 기계처럼 들립니다.
  - 합쇼체(~습니다)를 기본으로 하되 해요체 종결(~죠, ~거든요, ~인데요, ~예요)을 자연스럽게 섞습니다.
  - '-ㅂ니다/-습니다'로 끝나는 문장을 **3문장 이상 연달아 쓰지 않습니다.**
  - 장면마다 1문장 정도는 청자에게 말을 거는 수사 의문문으로 씁니다(예: "무엇이 달랐을까요?"). 반드시 물음표로 끝냅니다 — 물음표가 있어야 음성의 톤이 올라갑니다.

## 3. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
- 태그 안에는 코드 블록 표시(```)를 쓰지 말고 내용만 넣습니다.
- description은 영상 내용을 2~3문장으로 요약만 합니다. 구독 링크·브랜딩 줄은 시스템이 자동으로 덧붙이므로 직접 넣지 마세요.
- **title은 궁금증을 유발하는 훅을 앞에 두고 책 제목은 뒤에 배치합니다.** 형식: `{{훅}} — {{책 제목}}` (앞 15자 안에 호기심·결과·숫자 훅). 예: `140억을 만든 한 문장 — 피터 린치`. 책 제목을 앞세우지 마세요.
<scenes_json>
[{{"caption": "...", "narration": "...", "image_prompt": "english description"}}, {{"caption": "...", "narration": "...", "image_prompt": "...", "card": {{"type": "quote", "text": "...", "source": "..."}}}}, ...]
</scenes_json>
<video_meta>
{{"title": "...", "description": "...", "tags": ["..."], "thumbnail_copy": "...", "thumbnail_image_prompt": "english cinematic background, no text"}}
</video_meta>
- thumbnail_copy 는 썸네일에 크게 띄울 후킹 한 줄(16자 내외, 제목보다 짧고 강하게). thumbnail_image_prompt 는 썸네일 배경용 영어 묘사(시네마틱·고대비, 이미지 안에 글자 없음).
- **고유명사 검수.** 출력 전에 인명·지명·책 제목을 한 번 더 확인합니다 — 외국 저자명은 국내 출판 표지 표기(예: 보도 섀퍼, 모건 하우절), 지명은 통용 표기(예: 버몬트)로 씁니다. 오탈자가 제목·태그로 번지면 검색 유입이 통째로 사라집니다.
"""


_STYLE_HEADER = "\n## 4. 말투 스타일 (아래 샘플의 어조를 따르세요)\n"


def build_video_system_prompt(style_samples: list[str], scene_count: int = 8,
                              image_style_kw: str = "photorealistic, cinematic") -> str:
    sp = _rules(scene_count, image_style_kw)
    if style_samples:
        sp += _STYLE_HEADER
        for i, s in enumerate(style_samples, 1):
            sp += f"\n--- 샘플 {i} ---\n{s.strip()}\n"
    return sp


def build_video_user_message(topic: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"주제: {topic}", "", "시스템 규칙에 따라 YouTube 영상 대본을 장면 배열로 작성하세요."]
    refs = [s for s in sources if s.get("url")]
    if refs:
        lines.append("")
        lines.append("참고 링크:")
        for s in refs:
            note = f" — {s['note']}" if s.get("note") else ""
            lines.append(f"- {s['url']}{note}")
    lines.append("")
    lines.append("마지막 응답에 <scenes_json>...</scenes_json> 과 <video_meta>...</video_meta> 두 태그를 정확히 포함하세요.")
    return "\n".join(lines)


def _shorts_rules(scene_count: int, image_style_kw: str) -> str:
    return f"""당신은 한국어 세로형 쇼츠(Shorts/Reels) 영상 대본 작가입니다. 주제로 60초 이내 짧은 슬라이드쇼형 영상 대본을 만듭니다.

## 1. 리서치
- WebSearch·WebFetch 로 주제 관련 신뢰할 자료를 수집합니다.
- 사용자가 제공한 참고 링크가 있으면 반영합니다.
- 확인된 사실만 씁니다.

## 2. 구성
- 영상은 장면(scene) 약 {scene_count}개로 구성합니다.
- 세로형(9:16) 화면에 최적화합니다.
- 각 장면: caption(화면 헤드라인, 10자 이내), narration(1~2문장, 짧고 강렬하게).
- 각 장면에 image_prompt(영어, {image_style_kw} 스타일, 글자 없음)도 포함합니다.
- 모든 장면의 image_prompt는 색감·조명·분위기를 일관되게 유지합니다(같은 {image_style_kw} 톤).
- image_prompt는 자연스러운 실사 장면을 묘사합니다. **사람 얼굴은 되도록 넣지 않습니다**(생성 모델이 얼굴·눈·손을 기형으로 만드는 일이 잦음). 사람이 필요하면 **뒷모습·실루엣·원경**으로만 담고, 아니면 사물·풍경·정물로 표현합니다. **정면 얼굴·손 클로즈업 금지, 팔짱·턱 괴기 등 팔이 접히거나 교차하는 포즈 금지**(팔 기형 유발).
- 첫 장면에서 강렬하게 후킹. 마지막 장면은 핵심 메시지로 마무리. **구독·좋아요·팔로우 요청 멘트는 절대 넣지 않습니다.**
- 자연스러운 한국어 구어체. 문장은 마침표나 물음표로 끝냅니다. **'음·어·아' 같은 간투사·추임새는 쓰지 않습니다.**
- **문장 끝(어미)을 다양하게 씁니다** — ~습니다만 반복하지 말고 ~죠·~거든요·~인데요를 섞습니다. 첫 장면 후킹에는 수사 의문문(물음표 종결)이 효과적입니다.

## 3. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
- 태그 안에는 코드 블록 표시(```)를 쓰지 않습니다.
- description은 영상 내용을 1~2문장으로 요약만 합니다. 구독 링크·브랜딩 줄은 시스템이 자동으로 덧붙이므로 직접 넣지 마세요.
- **title은 궁금증을 유발하는 훅을 앞에 두고 책 제목은 뒤에 배치합니다.** 형식: `{{훅}} — {{책 제목}}` (앞 15자 안에 호기심·결과·숫자 훅). 책 제목을 앞세우지 마세요.
<scenes_json>
[{{"caption": "...", "narration": "...", "image_prompt": "english description"}}, ...]
</scenes_json>
<video_meta>
{{"title": "...", "description": "...", "tags": ["..."], "thumbnail_copy": "...", "thumbnail_image_prompt": "english cinematic background, no text"}}
</video_meta>
- thumbnail_copy 는 썸네일에 크게 띄울 후킹 한 줄(10자 내외, 쇼츠답게 더 짧고 강하게). thumbnail_image_prompt 는 썸네일 배경용 영어 묘사(시네마틱·고대비, 이미지 안에 글자 없음).
"""


def build_shorts_system_prompt(style_samples: list[str], scene_count: int = 5,
                                image_style_kw: str = "photorealistic, cinematic") -> str:
    sp = _shorts_rules(scene_count, image_style_kw)
    if style_samples:
        sp += _STYLE_HEADER
        for i, s in enumerate(style_samples, 1):
            sp += f"\n--- 샘플 {i} ---\n{s.strip()}\n"
    return sp


def build_shorts_user_message(topic: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"주제: {topic}", "", "세로형 쇼츠 대본을 장면 배열로 작성하세요."]
    refs = [s for s in sources if s.get("url")]
    if refs:
        lines.append("\n참고 링크:")
        for s in refs:
            note = f" — {s['note']}" if s.get("note") else ""
            lines.append(f"- {s['url']}{note}")
    lines.append("")
    lines.append("마지막 응답에 <scenes_json>...</scenes_json> 과 <video_meta>...</video_meta> 두 태그를 정확히 포함하세요.")
    return "\n".join(lines)
