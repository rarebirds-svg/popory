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


def test_append_subscribe_cta_no_brand_dup():
    """소급용은 구독 CTA만 붙이고 브랜드 줄은 중복시키지 않는다(옛 영상은 이미 브랜드 줄 보유)."""
    from popory_content.video_prompt import append_subscribe_cta, CHANNEL_SUB_URL, BRAND_LINE
    old = "책 요약입니다.\n포포리 책방 — 한 권의 책에서 길어올린 인생의 지혜."
    out = append_subscribe_cta(old)
    assert CHANNEL_SUB_URL in out
    assert out.count(BRAND_LINE) == 1        # 브랜드 줄 중복 없음
    assert append_subscribe_cta(out) == out  # 멱등


def test_video_and_shorts_prompts_avoid_faces():
    """2026-08 정책 전환 — 얼굴 허용에서 얼굴 회피로. 생성 모델이 얼굴·눈·손을 기형으로
    만드는 빈도가 높아, 사후 검수(image_review)로 거르기 전에 애초에 덜 만들게 유도한다."""
    from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
    for sp in (build_video_system_prompt([]), build_shorts_system_prompt([])):
        assert "얼굴은 되도록 넣지 않습니다" in sp   # 기본은 얼굴 회피
        assert "뒷모습" in sp and "실루엣" in sp     # 사람이 필요하면 이렇게
        assert "클로즈업" in sp                      # 정면 얼굴·손 클로즈업 금지
        assert "얼굴이 보여도" not in sp             # 옛 허용 문구가 남으면 안 된다
