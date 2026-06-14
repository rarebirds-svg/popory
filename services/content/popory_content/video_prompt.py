# claude CLI 에 줄 YouTube 영상 대본 system/user 프롬프트. 장면 배열 + 메타를 출력시킨다.
from typing import Any


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
- image_prompt는 자연스러운 실사 장면을 묘사합니다. 사람이 등장해도 좋고 **얼굴이 보여도 됩니다** — 단 **편안하고 자연스러운 표정**(찡그리거나 과장된 표정 금지), 해부학적으로 정상이고 온전한 인체(머리·손·신체가 잘리거나 기형이 되지 않게)로 표현합니다. 인물은 화면 안에 여백을 두고 자연스러운 거리(전신·상반신)에서 담으며, 과도한 얼굴·손 클로즈업은 피합니다.
- 도입(후킹) → 본문 → 마무리(여운 있는 정리) 흐름. **구독·좋아요·알림 등 채널 구독 요청 멘트는 절대 넣지 않습니다**(내레이션·마무리 모두).
- 자연스러운 한국어 구어체. 문장은 마침표로 끝냅니다. **'음·어·아·그' 같은 의미 없는 간투사·추임새는 쓰지 않습니다.**

## 3. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
- 태그 안에는 코드 블록 표시(```)를 쓰지 말고 내용만 넣습니다.
- description은 영상 내용을 2~3문장으로 요약한 뒤, **마지막 줄에 정확히 다음 브랜딩 한 줄을 그대로 넣습니다**: `포포리 책방 — 한 권의 책에서 길어올린 인생의 지혜.` 구독·좋아요·팔로우 요청 문구는 description에도 넣지 않습니다.
<scenes_json>
[{{"caption": "...", "narration": "...", "image_prompt": "english description"}}, ...]
</scenes_json>
<video_meta>
{{"title": "...", "description": "...", "tags": ["..."]}}
</video_meta>
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
- image_prompt는 자연스러운 실사 장면을 묘사합니다. 사람이 등장해도 좋고 얼굴이 보여도 되되 **편안하고 자연스러운 표정**, 해부학적으로 정상이고 온전한 인체로 표현합니다. 인물은 자연스러운 거리에서 담고 과도한 얼굴·손 클로즈업은 피합니다.
- 첫 장면에서 강렬하게 후킹. 마지막 장면은 핵심 메시지로 마무리. **구독·좋아요·팔로우 요청 멘트는 절대 넣지 않습니다.**
- 자연스러운 한국어 구어체. **'음·어·아' 같은 간투사·추임새는 쓰지 않습니다.**

## 3. 출력 (반드시 마지막 응답에 두 태그를 정확히 포함)
- 태그 안에는 코드 블록 표시(```)를 쓰지 않습니다.
- description은 영상 내용을 1~2문장으로 요약한 뒤 **마지막 줄에 정확히** `포포리 책방 — 한 권의 책에서 길어올린 인생의 지혜.` 를 그대로 넣습니다. 구독·좋아요·팔로우 문구는 넣지 않습니다.
<scenes_json>
[{{"caption": "...", "narration": "...", "image_prompt": "english description"}}, ...]
</scenes_json>
<video_meta>
{{"title": "...", "description": "...", "tags": ["..."]}}
</video_meta>
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
