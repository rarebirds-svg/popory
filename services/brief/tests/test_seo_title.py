# 제목 SEO 정규화 — 말머리·날짜를 앞에서 걷어내고 발행 꼬리를 뒤에 붙인다. 키워드 없는 제목은 fallback.
import datetime
import textwrap

import pytest

from popory_brief import seo_title as st
from popory_brief.categories import load_category
from popory_brief.seo_rules import seo_rules


def test_date_label_weekly_and_daily():
    assert st.date_label(datetime.date(2026, 9, 5), weekly=True) == "9월 1주차"
    assert st.date_label(datetime.date(2026, 9, 8), weekly=True) == "9월 2주차"
    assert st.date_label(datetime.date(2026, 9, 30), weekly=True) == "9월 5주차"
    assert st.date_label(datetime.date(2026, 9, 4), weekly=False) == "9월 4일"
    assert st.date_label(datetime.date(2026, 12, 25), weekly=False) == "12월 25일"


@pytest.mark.parametrize("raw, core", [
    ("[부동산 주간 이슈 브리핑] 2026-09-05(당일 브리핑 및 주간브리핑 포함)", ""),
    ("[부동산 이슈 브리핑] 2026-09-04 ① 세제개편 후폭풍", "세제개편 후폭풍"),
    ("[Legal AI 이슈 브리핑] 2026-09-05 EU AI법 시행 D-30", "EU AI법 시행 D-30"),
    ("2026.09.05 [부동산] 개포우성7차 통합심의 통과", "개포우성7차 통합심의 통과"),
    ("9월 5일 - 종부세 1주택 실거주 공제 확대", "종부세 1주택 실거주 공제 확대"),
    ("(2026-09-05) 종부세 개편", "종부세 개편"),
    ("개포우성7차 재건축 통과 | 9월 1주차 부동산 브리핑", "개포우성7차 재건축 통과 | 9월 1주차 부동산 브리핑"),
    ("", ""),
])
def test_strip_boilerplate(raw, core):
    assert st.strip_boilerplate(raw) == core


def test_normalize_appends_suffix_when_keywords_remain():
    out = st.normalize_title("[부동산 이슈 브리핑] 2026-09-04 ① 세제개편 후폭풍 종부세 실거주 공제",
                             suffix="9월 4일 부동산 브리핑", fallback="[부동산 이슈 브리핑] 2026-09-04")
    assert out == "세제개편 후폭풍 종부세 실거주 공제 | 9월 4일 부동산 브리핑"
    assert st.keyword_part(out) == "세제개편 후폭풍 종부세 실거주 공제"


def test_normalize_keeps_llm_suffix_and_clean_titles_untouched():
    good = "개포우성7차 가락삼익 재건축 통과와 코인 매각 주택 매수 분석 | 9월 1주차 부동산 브리핑"
    assert st.normalize_title(good, suffix="다른 꼬리", fallback="x") == good
    assert st.normalize_title("종부세 개편", suffix="", fallback="x") == "종부세 개편"


def test_normalize_falls_back_when_only_boilerplate():
    fb = "[부동산 주간 이슈 브리핑] 2026-09-05"
    assert st.normalize_title("[부동산 주간 이슈 브리핑] 2026-09-05(당일 브리핑 및 주간브리핑 포함)",
                              suffix="9월 1주차 부동산 브리핑", fallback=fb) == fb
    assert st.normalize_title("", suffix="s", fallback=fb) == fb
    assert st.normalize_title("[X] 2026-09-05 (2026.09.05)", suffix="s", fallback=fb) == fb


def _cat(tmp_path, slug, extra=""):
    d = tmp_path / slug
    d.mkdir()
    (d / "SKILL.md").write_text(textwrap.dedent(f"""\
        ---
        slug: {slug}
        name: 부동산
        delivery_mode: standalone
        subject_template: "[{{name}} 주간 이슈 브리핑] {{date}}"
        sender_name: "{{name}}"
        enabled: true
        {extra}
        ---
        본문 프롬프트
        """), encoding="utf-8")
    return load_category(slug, root=tmp_path)


def test_category_title_suffix_weekly_default(tmp_path):
    c = _cat(tmp_path, "realestate", "days: sat")
    assert c.weekly is True
    assert c.title_suffix(datetime.date(2026, 9, 5)) == "9월 1주차 부동산 브리핑"


def test_category_title_suffix_daily_and_custom(tmp_path):
    c = _cat(tmp_path, "daily", "days: mon,tue,wed")
    assert c.weekly is False
    assert c.title_suffix(datetime.date(2026, 9, 4)) == "9월 4일 부동산 브리핑"
    c2 = _cat(tmp_path, "custom", 'seo_suffix: "{date_label} {name} 데일리 PICK 5"')
    assert c2.title_suffix(datetime.date(2026, 9, 4)) == "9월 4일 부동산 데일리 PICK 5"


def test_category_rejects_blank_seo_suffix(tmp_path):
    with pytest.raises(ValueError, match="seo_suffix"):
        _cat(tmp_path, "blank", 'seo_suffix: "  "')


def test_seo_rules_carry_suffix_and_structure_rules(tmp_path):
    c = _cat(tmp_path, "realestate", "days: sat")
    text = seo_rules(c, datetime.date(2026, 9, 5))
    assert "| 9월 1주차 부동산 브리핑" in text
    assert "첫 15자" in text and "## 정리" in text and "4~6회" in text and "표" in text
    assert "[부동산 브리핑]" in text and "2026-09-05" in text   # 금지 예시가 실제 값으로 채워진다
    assert "{" not in text.replace("{핵심", "").replace("{{", "")  # 미치환 자리표시자 없음


def test_seo_body_false_drops_structure_rules(tmp_path):
    c = _cat(tmp_path, "msg", "seo_body: false")
    text = seo_rules(c, datetime.date(2026, 9, 4))
    assert "| 9월 4일 부동산 브리핑" in text and "첫 15자" in text
    assert "## 정리" not in text and "표 2개" not in text
    assert c.seo_body is False and _cat(tmp_path, "dflt").seo_body is True


def test_real_categories_declare_seo_shape():
    from popory_brief.categories import load_category as real
    pick5 = real("realestate-pick5")
    assert pick5.seo_body is False
    assert pick5.title_suffix(datetime.date(2026, 9, 4)) == "9월 4일 부동산 데일리 뉴스 PICK 5"
    blog = real("realestate-pick5-blog")
    assert blog.seo_body is True and blog.title_suffix(datetime.date(2026, 9, 4)) == "9월 4일 부동산 데일리 뉴스 PICK 5"
    weekly = real("realestate")
    assert weekly.weekly and weekly.title_suffix(datetime.date(2026, 9, 5)) == "9월 1주차 부동산 브리핑"
    # 옛 말머리 형식이 어느 SKILL.md 의 title 예시에도 남아 있지 않다.
    for slug in ("realestate", "legal-ai", "naver", "geopolitics", "antitrust", "anticorruption",
                 "realestate-pick5", "realestate-pick5-blog"):
        sp = real(slug).system_prompt
        assert '"title": "[' not in sp, slug
        assert "| " in sp and "시작 금지" in sp, slug
