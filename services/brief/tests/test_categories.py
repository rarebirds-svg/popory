# popory_brief.categories 단위 테스트.
"""SKILL.md 스캔·파싱·검증 + 카테고리 분류 동작 확인."""
from __future__ import annotations
from pathlib import Path
import textwrap
import pytest

from popory_brief import categories


def _write_skill(
    tmp_path: Path,
    dir_name: str,
    frontmatter_yaml: str | None = None,
    body: str = "system prompt body\n",
) -> Path:
    skill_dir = tmp_path / dir_name
    skill_dir.mkdir()
    fm = frontmatter_yaml if frontmatter_yaml is not None else textwrap.dedent(f"""\
        slug: {dir_name}
        name: {dir_name.title()}
        delivery_mode: standalone
        subject_template: "[{{name}}] {{date}}"
        sender_name: "{{name}} bot"
        enabled: true
        """)
    (skill_dir / "SKILL.md").write_text(f"---\n{fm}---\n\n{body}", encoding="utf-8")
    return skill_dir / "SKILL.md"


def test_scan_returns_category(tmp_path):
    _write_skill(tmp_path, "foo")
    cats = categories._scan(tmp_path)
    assert len(cats) == 1
    c = cats[0]
    assert c.slug == "foo"
    assert c.name == "Foo"
    assert c.delivery_mode == "standalone"
    assert c.area == "brief-foo"
    assert "system prompt body" in c.system_prompt
    assert c.enabled is True


def test_subject_and_sender_format(tmp_path):
    _write_skill(tmp_path, "foo")
    c = categories._scan(tmp_path)[0]
    assert c.subject("2026-05-31") == "[Foo] 2026-05-31"
    assert c.sender() == "Foo bot"


def test_missing_required_field_raises(tmp_path):
    fm = "slug: foo\nname: Foo\ndelivery_mode: standalone\nenabled: true\n"
    _write_skill(tmp_path, "foo", frontmatter_yaml=fm)
    with pytest.raises(ValueError, match="missing fields"):
        categories._scan(tmp_path)


def test_invalid_slug_raises(tmp_path):
    fm = textwrap.dedent("""\
        slug: "Bad_Slug"
        name: x
        delivery_mode: standalone
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """)
    _write_skill(tmp_path, "anydir", frontmatter_yaml=fm)
    with pytest.raises(ValueError, match="invalid slug"):
        categories._scan(tmp_path)


def test_invalid_delivery_mode_raises(tmp_path):
    fm = textwrap.dedent("""\
        slug: foo
        name: Foo
        delivery_mode: weekly
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """)
    _write_skill(tmp_path, "foo", frontmatter_yaml=fm)
    with pytest.raises(ValueError, match="invalid delivery_mode"):
        categories._scan(tmp_path)


def test_duplicate_slug_raises(tmp_path):
    _write_skill(tmp_path, "dir1", frontmatter_yaml=textwrap.dedent("""\
        slug: same
        name: A
        delivery_mode: standalone
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """))
    _write_skill(tmp_path, "dir2", frontmatter_yaml=textwrap.dedent("""\
        slug: same
        name: B
        delivery_mode: bundled
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """))
    with pytest.raises(ValueError, match="duplicate slug"):
        categories._scan(tmp_path)


def test_missing_frontmatter_raises(tmp_path):
    skill_dir = tmp_path / "foo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frontmatter not found"):
        categories._scan(tmp_path)


def test_enabled_filter(tmp_path):
    _write_skill(tmp_path, "active")
    _write_skill(tmp_path, "inactive", frontmatter_yaml=textwrap.dedent("""\
        slug: inactive
        name: Inactive
        delivery_mode: standalone
        subject_template: "x"
        sender_name: "x"
        enabled: false
        """))
    cats = categories.list_categories(tmp_path)
    assert [c.slug for c in cats] == ["active"]


def test_standalone_and_bundled_filters(tmp_path):
    _write_skill(tmp_path, "alpha", frontmatter_yaml=textwrap.dedent("""\
        slug: alpha
        name: Alpha
        delivery_mode: standalone
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """))
    _write_skill(tmp_path, "beta", frontmatter_yaml=textwrap.dedent("""\
        slug: beta
        name: Beta
        delivery_mode: bundled
        subject_template: "x"
        sender_name: "x"
        enabled: true
        """))
    assert [c.slug for c in categories.standalone_categories(tmp_path)] == ["alpha"]
    assert [c.slug for c in categories.bundled_categories(tmp_path)] == ["beta"]


def test_load_category_by_slug(tmp_path):
    _write_skill(tmp_path, "foo")
    c = categories.load_category("foo", tmp_path)
    assert c.name == "Foo"


def test_load_category_unknown_raises(tmp_path):
    with pytest.raises(KeyError, match="missing"):
        categories.load_category("missing", tmp_path)
