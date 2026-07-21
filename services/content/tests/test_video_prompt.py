# 영상 대본 system prompt 가 장면·메타 출력 계약을 담는지 검증.
from popory_content.video_prompt import build_video_system_prompt, build_video_user_message


def test_system_prompt_has_contract():
    sp = build_video_system_prompt([], scene_count=12, image_style_kw="watercolor painting")
    assert "scenes_json" in sp
    assert "video_meta" in sp
    assert "narration" in sp
    assert "caption" in sp
    assert "image_prompt" in sp
    assert "12" in sp
    assert "watercolor" in sp


def test_system_prompt_embeds_style():
    sp = build_video_system_prompt(["내 말투 샘플"])
    assert "내 말투 샘플" in sp


def test_user_message_has_topic():
    um = build_video_user_message("사피엔스 요약", [])
    assert "사피엔스 요약" in um
    assert "scenes_json" in um


from popory_content.video_prompt import build_shorts_system_prompt, build_shorts_user_message


def test_build_shorts_system_prompt_includes_shorts_rules():
    sp = build_shorts_system_prompt([], scene_count=5, image_style_kw="photorealistic")
    assert "쇼츠" in sp or "Shorts" in sp
    assert "5" in sp
    assert "세로형" in sp or "60초" in sp


def test_build_shorts_user_message_includes_topic():
    msg = build_shorts_user_message("전세사기 예방", [])
    assert "전세사기 예방" in msg
    assert "scenes_json" in msg


def test_system_prompt_demands_consistent_style_suffix():
    from popory_content.video_prompt import build_video_system_prompt
    sp = build_video_system_prompt([], scene_count=8, image_style_kw="watercolor painting")
    # 모든 장면이 같은 톤이 되도록 '일관된'/'동일' 류 지시가 image_prompt 규칙에 있어야 한다
    assert "일관" in sp
    assert "watercolor painting" in sp


def test_narration_still_bans_subscribe_cta():
    """내레이션엔 여전히 구독 요청 금지(브랜딩 유지). 설명란 CTA는 파싱 단계에서 append."""
    from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
    for sp in (build_video_system_prompt([]), build_shorts_system_prompt([])):
        assert "구독" in sp and "절대 넣지 않습니다" in sp   # 내레이션 CTA 금지 유지
        # 설명란은 요약만 시키고 브랜딩/구독은 자동 append (프롬프트에서 강제 브랜딩 줄 제거)
        assert "자동으로 덧붙" in sp


def test_title_rule_hook_first():
    """제목은 훅을 앞에, 책 제목을 뒤에 배치하도록 지시."""
    from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
    for sp in (build_video_system_prompt([]), build_shorts_system_prompt([])):
        assert "훅을 앞" in sp
        assert "책 제목은 뒤" in sp


def test_append_description_cta():
    """설명란 요약 뒤에 구독 링크·브랜딩을 붙이고, 멱등(중복 append 안 함)."""
    from popory_content.video_prompt import append_description_cta, CHANNEL_SUB_URL, BRAND_LINE
    out = append_description_cta("책 요약입니다.")
    assert "책 요약입니다." in out
    assert CHANNEL_SUB_URL in out and "sub_confirmation=1" in out
    assert BRAND_LINE in out
    assert append_description_cta(out) == out          # 멱등
    assert append_description_cta("") .startswith("매일")  # 빈 설명도 CTA는 붙음


def test_video_and_shorts_prompts_allow_natural_faces():
    """SDXL은 얼굴을 잘 그리므로 얼굴 허용 — 단 자연스러운 표정·정상 인체로 유도."""
    from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
    for sp in (build_video_system_prompt([]), build_shorts_system_prompt([])):
        assert "얼굴이 보여도" in sp        # 얼굴 허용
        assert "자연스러운 표정" in sp      # 무서운/과장 표정 방지
        assert "정상" in sp                 # 해부학적 정상 인체
