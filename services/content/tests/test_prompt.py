# system prompt 가 스타일 샘플·핵심 규칙을 담는지, user message 가 주제·출처를 담는지 검증.
from popory_content.prompt import build_system_prompt, build_user_message


def test_system_prompt_embeds_samples_and_rules():
    sp = build_system_prompt(["내 글 샘플 본문입니다."])
    assert "내 글 샘플 본문입니다." in sp
    assert "네이버" in sp
    assert "저작권" in sp
    assert "draft_markdown" in sp
    assert "meta_json" in sp


def test_system_prompt_without_samples():
    sp = build_system_prompt([])
    assert "draft_markdown" in sp


def test_user_message_has_topic_and_sources():
    um = build_user_message("전세사기 예방", [{"url": "https://law.go.kr/x", "note": "근거"}])
    assert "전세사기 예방" in um
    assert "https://law.go.kr/x" in um
