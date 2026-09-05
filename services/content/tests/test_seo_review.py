# SEO·AEO·GEO 검토 — 점수·문제를 meta 에 싣고, 교정본은 검증 통과 시에만 채택하며, 검토기 실패는 fail-open.
from popory_content import seo_review as sr
from popory_content.generate import GenerateError

_HTML = "<h2>돈의 심리학이란</h2><p>" + "부는 보이지 않는다. " * 30 + "</p>"


def _runner_with(review_json: str, revised: str, tag="revised_html"):
    def runner(*, system_prompt, user_msg, parse, **kw):
        runner.calls.append({"sp": system_prompt, "um": user_msg, "kw": kw})
        return parse(f"잡담\n<seo_review>{review_json}</seo_review>\n<{tag}>{revised}</{tag}>")
    runner.calls = []
    return runner


def test_review_blog_adopts_valid_revision_and_scores():
    rev = _HTML + "<h2>자주 묻는 질문</h2><h3>어떤 책인가요?</h3><p>답입니다.</p>"
    runner = _runner_with('{"seo":{"score":70,"issues":["질문형 소제목 없음"]},"aeo":{"score":50,"issues":["FAQ 없음"]},'
                          '"geo":{"score":90,"issues":[]},"revised_title":"부는 왜 보이지 않을까 — 돈의 심리학","revised_tags":["돈의 심리학","모건 하우절"],"summary":"FAQ 보강"}', rev)
    body, meta = sr.review_blog(_HTML, {"title": "돈의 심리학", "tags": ["책"]}, topic="돈의 심리학", job_id="j", runner=runner)
    assert body == rev
    assert meta["title"].startswith("부는 왜") and meta["tags"] == ["돈의 심리학", "모건 하우절"]
    r = meta["seo_review"]
    assert r["status"] == "ok" and r["revised"] is True and r["overall"] == 70
    assert r["aeo"]["issues"] == ["FAQ 없음"] and r["seo"]["score"] == 70
    assert "AEO" in runner.calls[0]["sp"] and "GEO" in runner.calls[0]["sp"]
    assert "돈의 심리학" in runner.calls[0]["um"] and _HTML in runner.calls[0]["um"]


def test_review_blog_keeps_original_when_revision_is_empty_or_broken():
    base = '{"seo":{"score":95,"issues":[]},"aeo":{"score":90,"issues":[]},"geo":{"score":92,"issues":[]},"revised_title":"새 제목","revised_tags":null,"summary":"양호"}'
    body, meta = sr.review_blog(_HTML, {"title": "t"}, topic="x", runner=_runner_with(base, ""))
    assert body == _HTML and meta["title"] == "t"          # 교정 없음 → 제목도 안 바뀐다
    assert meta["seo_review"]["revised"] is False and meta["seo_review"]["overall"] == 92
    body, _ = sr.review_blog(_HTML, {}, topic="x", runner=_runner_with(base, "<p>짧게 잘림</p>"))
    assert body == _HTML                                    # 70% 미만으로 줄면 거부
    body, _ = sr.review_blog(_HTML, {}, topic="x", runner=_runner_with(base, _HTML + "<script>x</script>"))
    assert body == _HTML                                    # 금지 태그 거부


def test_review_blog_fail_open_and_disabled(monkeypatch):
    def boom(**kw):
        raise GenerateError("cli down")
    body, meta = sr.review_blog(_HTML, {"title": "t"}, topic="x", runner=boom)
    assert body == _HTML and meta["seo_review"]["status"] == "unavailable" and meta["title"] == "t"
    monkeypatch.setattr(sr, "ENABLED", False)
    body, meta = sr.review_blog(_HTML, {}, topic="x", runner=lambda **kw: 1/0)
    assert body == _HTML and meta["seo_review"]["status"] == "disabled"


def test_parse_tolerates_missing_axes_and_bad_scores():
    parse = sr._parse(sr._HTML_TAG)
    out = parse('<seo_review>{"seo":{"score":"88","issues":"x"},"geo":{"score":200,"issues":["a"]}}</seo_review>')
    assert out["seo"] == {"score": 88, "issues": []}
    assert out["aeo"] == {"score": None, "issues": []}
    assert out["geo"]["score"] == 100 and out["overall"] == 94
    assert out["revised_body"] == "" and out["revised_title"] is None


def test_review_youtube_post_uses_post_tag():
    post = '"부는 보이지 않는다"\n\n— 『돈의 심리학』 모건 하우절\n\n오늘도 조용히 쌓아가요.\n\n#오늘의문장 #포포리책방'
    rev = post.replace("#포포리책방", "#포포리책방 #돈의심리학 #모건하우절")
    runner = _runner_with('{"seo":{"score":60,"issues":["해시태그 부족"]},"aeo":{"score":80,"issues":[]},"geo":{"score":85,"issues":[]},"summary":"태그 보강"}', rev, tag="revised_post")
    body, meta = sr.review_youtube_post(post, {"book": "돈의 심리학"}, topic="돈의 심리학 - 모건 하우절", runner=runner)
    assert body == rev and meta["seo_review"]["revised"] is True and meta["book"] == "돈의 심리학"
    assert "커뮤니티 게시글" in runner.calls[0]["sp"]
