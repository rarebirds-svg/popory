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


def test_longform_cta_only_in_ending_scene_and_shorts_still_ban():
    """2026-09 정책: 롱폼은 마지막 장면(엔딩 CTA)에만 구독·좋아요·댓글·추천 영상 3단계를 넣고
    본문 장면엔 넣지 않는다. 쇼츠는 여전히 전면 금지. 설명란 CTA는 파싱 단계에서 append."""
    from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
    long_sp = build_video_system_prompt([])
    assert "엔딩 CTA" in long_sp and "마지막 장면에만" in long_sp
    assert "댓글로 자유롭게" in long_sp and "화면에 보이는 추천 영상" in long_sp
    assert "다른 영상 제목을 지어내지" in long_sp   # 추천 영상 제목 환각 금지
    shorts_sp = build_shorts_system_prompt([])
    assert "구독" in shorts_sp and "절대 넣지 않습니다" in shorts_sp
    for sp in (long_sp, shorts_sp):
        # 설명란은 요약만 시키고 브랜딩/구독은 자동 append (프롬프트에서 강제 브랜딩 줄 제거)
        assert "자동으로 덧붙" in sp


def test_longform_prehook_and_cards():
    """프리후크(첫 문장 결론), 카드(stat/quote/keypoints) 규칙이 롱폼 프롬프트에 있다."""
    from popory_content.video_prompt import build_video_system_prompt
    sp = build_video_system_prompt([], scene_count=16)
    assert "프리후크" in sp and "첫 문장에" in sp
    assert '"type": "quote"' in sp and '"type": "keypoints"' in sp and '"type": "stat"' in sp
    assert "확인된 수치만" in sp   # 숫자 카드 환각 금지
    assert "확인된 문장만" in sp   # 명언 카드 환각 금지
    assert "고유명사 검수" in sp


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


def test_narration_demands_ending_variety():
    """2026-08 톤 단조로움 개선 — 문장별 TTS 합성이라 어미가 같으면 모든 문장이 같은 억양으로
    끝난다. 어미 다양화(해요체 혼용·수사 의문문)를 프롬프트에서 강제한다."""
    from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
    for sp in (build_video_system_prompt([]), build_shorts_system_prompt([])):
        assert "어미" in sp and "다양하게" in sp     # 어미 다양화 지시
        assert "물음표" in sp                        # 수사 의문문(상승조) 유도
        assert "~죠" in sp                           # 해요체 혼용 예시
    sp = build_video_system_prompt([])
    assert "3문장 이상 연달아" in sp                 # 같은 어미 3연속 금지(롱폼)
    assert "콜론 종결 금지" in sp                    # 마침표·물음표 외 종결 금지 유지


def test_video_and_shorts_prompts_avoid_faces():
    """2026-08 정책 전환 — 얼굴 허용에서 얼굴 회피로. 생성 모델이 얼굴·눈·손을 기형으로
    만드는 빈도가 높아, 사후 검수(image_review)로 거르기 전에 애초에 덜 만들게 유도한다."""
    from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
    for sp in (build_video_system_prompt([]), build_shorts_system_prompt([])):
        assert "얼굴은 되도록 넣지 않습니다" in sp   # 기본은 얼굴 회피
        assert "뒷모습" in sp and "실루엣" in sp     # 사람이 필요하면 이렇게
        assert "클로즈업" in sp                      # 정면 얼굴·손 클로즈업 금지
        assert "얼굴이 보여도" not in sp             # 옛 허용 문구가 남으면 안 된다


def test_prehook_rule_forbids_the_openers_seen_in_real_scripts():
    """실제 대본 10편에서 나온 위반 유형(인물 소개·질문 시작·상황 묘사)이 금지로 명시돼 있고 좋은 예가 여러 유형이다."""
    from popory_content.video_prompt import build_video_system_prompt
    sp = build_video_system_prompt([], scene_count=16)
    assert "금지하는 시작" in sp
    for banned in ("인물·상황 소개", "질문으로 여는 문장", "인사", "서정적인 배경 묘사"):
        assert banned in sp
    for kind in ("결과 선공개", "충격적인 수치", "극적인 대비", "도발적인 주장"):
        assert kind in sp
    assert "60자 안쪽" in sp                       # 첫 문장 길이 상한
    assert "지어내지 않고" in sp                    # 결과를 위해 없는 사실을 만들지 않는다
    assert "그대로 가져다 쓰지도" in sp             # 예시 문장 복붙 방지


def test_style_samples_cannot_override_prehook_in_longform():
    """말투 샘플은 프롬프트 맨 끝에 붙는다 — 어조만 따르고 첫 장면 구성은 프리후크가 우선이라고 못 박는다."""
    from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
    sp = build_video_system_prompt(["서정적으로 시작하는 샘플 글"], scene_count=16)
    tail = sp[sp.index("## 말투 스타일"):]
    assert "어조와 어미만" in tail and "프리후크 규칙이 항상 우선" in tail
    # 쇼츠는 별도 규칙이라 이 문구를 쓰지 않는다
    assert "프리후크 규칙이 항상 우선" not in build_shorts_system_prompt(["샘플"], scene_count=5)


def test_longform_user_message_repeats_the_hook_rule_last():
    from popory_content.video_prompt import build_video_user_message
    msg = build_video_user_message("돈의 심리학", [])
    assert "첫 문장은 인물·상황 소개나 질문이 아니라" in msg
    assert msg.rstrip().endswith("두 태그를 정확히 포함하세요.")   # 출력 형식 지시는 여전히 마지막


def test_longform_is_designed_as_a_story_not_a_summary():
    """2026-11 스토리 구성 재점검 — 목차 요약이 아니라 이야기로 설계하게 한다(약속·뼈대·열린 고리·실천)."""
    from popory_content.video_prompt import build_video_system_prompt
    sp = build_video_system_prompt([], scene_count=16)
    assert "한 문장 약속" in sp and "열린 고리" in sp
    for kind in ("person", "principles", "mystery"):          # 책 성격에 맞는 뼈대를 고른다
        assert kind in sp
    assert '"story_type"' in sp and '"promise"' in sp          # 어떤 뼈대를 골랐는지 meta 에 남긴다
    assert "장면마다 길이를 다르게" in sp and "약 9분" in sp      # 16장면 × 35초 ≈ 9분, 리듬은 다르게
    assert "오늘 바로 할 수 있는 한 가지" in sp                   # 끝에서 두 번째 장면: 정리와 실천
    assert "피사체와 구도는 장면마다 다르게" in sp               # 같은 정물만 되풀이하지 않는다


def test_longform_drops_the_mechanical_devices():
    """정해진 간격의 요약·장면마다 넣는 수사 의문문·목차 예고는 틀이 보여 뺐다. 대신 장면 끝이 다음 장면을 당긴다."""
    from popory_content.video_prompt import build_video_system_prompt
    sp = build_video_system_prompt([], scene_count=16)
    assert "3~4장면마다" not in sp
    assert "장면마다 1문장 정도는" not in sp
    assert "목차 안내가 아니라" in sp                            # '오늘 영상에서는 …을 정리해 드립니다' 금지
    assert "장면의 끝이 다음 장면을 보게" in sp
    assert "정말 답이 궁금할 때만" in sp
    assert "세 문장 안팎" in sp                                  # 엔딩 CTA 는 짧게


def test_shorts_carry_one_idea_with_a_short_hook_and_no_soft_ending():
    """쇼츠는 책 전체 요약이 아니라 한 가지만 — 첫 문장 30자 훅, 소개·인사로 열지 않기, 맥 빠지는 마무리 금지."""
    from popory_content.video_prompt import build_shorts_system_prompt, build_shorts_user_message
    sp = build_shorts_system_prompt([], scene_count=8)
    assert "한 편에 한 가지만" in sp
    assert "30자 안쪽" in sp and "인사, 책·저자 소개" in sp
    assert "훅(첫 장면)" in sp and "고리(마지막 장면)" in sp
    assert "맥 빠지는 마무리" in sp
    um = build_shorts_user_message("돈의 심리학", [])
    assert "한 가지만" in um and "30자 안쪽" in um              # 가장 나중에 읽히는 자리에서 한 번 더


def test_longform_asks_for_several_images_per_scene_and_shorts_do_not():
    """롱폼은 장면마다 그림 1~3장(image_prompts 배열)을 내레이션 순서대로 — 한 장으로 30초를 버티지 않는다."""
    from popory_content.video_prompt import build_video_system_prompt, build_shorts_system_prompt
    sp = build_video_system_prompt([], scene_count=16)
    assert '"image_prompts": [' in sp and "약 10초" in sp and "1~3개" in sp
    assert "image_prompts" not in build_shorts_system_prompt([])      # 쇼츠 장면은 7초 안팎이라 한 장 그대로
