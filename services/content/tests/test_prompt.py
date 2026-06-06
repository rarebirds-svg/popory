# system prompt 가 HTML·이미지·영상·출처 규칙과 스타일 샘플을 담는지, user message 가 주제·출처를 담는지 검증.
from popory_content.prompt import build_system_prompt, build_user_message


def test_system_prompt_embeds_samples_and_rules():
    sp = build_system_prompt(["내 글 샘플 본문입니다."])
    assert "내 글 샘플 본문입니다." in sp
    assert "figure" in sp            # 이미지 임베드 규칙
    assert "youtube" in sp.lower()   # 영상 임베드 규칙
    assert "출처" in sp              # 출처 표기
    assert "저작권" in sp
    assert "draft_html" in sp        # 출력 계약
    assert "meta_json" in sp


def test_system_prompt_without_samples():
    sp = build_system_prompt([])
    assert "draft_html" in sp


def test_user_message_has_topic_and_sources():
    um = build_user_message("전세사기 예방", [{"url": "https://law.go.kr/x", "note": "근거"}])
    assert "전세사기 예방" in um
    assert "https://law.go.kr/x" in um
    assert "draft_html" in um
