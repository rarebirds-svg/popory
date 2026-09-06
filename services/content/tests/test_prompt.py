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


def test_system_prompt_carries_seo_title_heading_and_caption_rules():
    sp = build_system_prompt([])
    assert "첫 15자" in sp and "[책 리뷰]" in sp and "핵심 요약 및 서평" in sp   # 제목: 검색어가 앞, 말머리 금지
    assert "5~8개" in sp and "굵은 <p>" in sp                                   # 소제목(H태그) 개수·볼드 대체 금지
    assert "4~6회" in sp and "결론부에 1회" in sp                               # 키워드 배치
    assert "사진 설명" in sp and "figcaption" in sp                            # 이미지 캡션에 검색어
    assert '"keyword"' in sp                                                    # meta 에 핵심 검색어
