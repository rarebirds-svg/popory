# popory_brief.markdown: Markdown → 메일용 HTML envelope
from popory_brief.markdown import markdown_to_email_html


def test_paragraph_and_link():
    html = markdown_to_email_html("안녕하세요. [예시](https://example.com)")
    assert "<p>" in html
    assert 'href="https://example.com"' in html
    assert "<!doctype html>" in html.lower()
    assert "<style>" in html  # envelope CSS 블록 포함


def test_table_renders_with_gfm():
    src = "| a | b |\n|---|---|\n| 1 | 2 |\n"
    html = markdown_to_email_html(src)
    assert "<table" in html
    assert "<th>a</th>" in html
    assert "<td>1</td>" in html


def test_code_fence_renders():
    src = "```python\nprint('x')\n```\n"
    html = markdown_to_email_html(src)
    assert "<pre>" in html
    assert "print(" in html


def test_h1_in_input_is_preserved_but_caller_should_avoid():
    # 본문 컨벤션은 H1 미사용. 코드는 거부하지 않고 그대로 변환만 한다.
    html = markdown_to_email_html("# title\n\n본문\n")
    assert "<h1>title</h1>" in html
