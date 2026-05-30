# popory_brief.categories — SKILL.md 디렉토리 스캔과 카테고리 메타 로드.
"""
services/brief/categories/{slug}/SKILL.md 디렉토리를 스캔해 활성 카테고리 목록을 반환.

API.
    list_categories(root=ROOT) -> list[Category]      # enabled 만
    load_category(slug, root=ROOT) -> Category        # 단일 (enabled 무시)
    standalone_categories(root=ROOT) -> list[Category]
    bundled_categories(root=ROOT) -> list[Category]
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parent.parent / "categories"
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
VALID_MODES = {"standalone", "bundled"}
REQUIRED = ("slug", "name", "delivery_mode", "subject_template", "sender_name", "enabled")


@dataclass(frozen=True)
class Category:
    slug: str
    name: str
    delivery_mode: str
    subject_template: str
    sender_name: str
    enabled: bool
    system_prompt: str

    @property
    def area(self) -> str:
        return f"brief-{self.slug}"

    def subject(self, date: str) -> str:
        return self.subject_template.format(name=self.name, date=date)

    def sender(self) -> str:
        return self.sender_name.format(name=self.name)


def _parse_skill_md(path: Path) -> Category:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: frontmatter not found")
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError(f"{path}: frontmatter not closed")
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip()
    missing = [k for k in REQUIRED if k not in meta]
    if missing:
        raise ValueError(f"{path}: missing fields: {missing}")
    if not SLUG_RE.match(str(meta["slug"])):
        raise ValueError(f"{path}: invalid slug {meta['slug']!r}")
    if meta["delivery_mode"] not in VALID_MODES:
        raise ValueError(f"{path}: invalid delivery_mode {meta['delivery_mode']!r}")
    return Category(
        slug=str(meta["slug"]),
        name=str(meta["name"]),
        delivery_mode=str(meta["delivery_mode"]),
        subject_template=str(meta["subject_template"]),
        sender_name=str(meta["sender_name"]),
        enabled=bool(meta["enabled"]),
        system_prompt=body,
    )


def _scan(root: Path = ROOT) -> list[Category]:
    if not root.exists():
        return []
    cats: list[Category] = []
    seen: set[str] = set()
    for skill_path in sorted(root.glob("*/SKILL.md")):
        cat = _parse_skill_md(skill_path)
        if cat.slug in seen:
            raise ValueError(f"duplicate slug {cat.slug!r}")
        seen.add(cat.slug)
        cats.append(cat)
    return cats


def list_categories(root: Path = ROOT) -> list[Category]:
    return [c for c in _scan(root) if c.enabled]


def load_category(slug: str, root: Path = ROOT) -> Category:
    for c in _scan(root):
        if c.slug == slug:
            return c
    raise KeyError(f"category {slug!r} not found")


def standalone_categories(root: Path = ROOT) -> list[Category]:
    return [c for c in list_categories(root) if c.delivery_mode == "standalone"]


def bundled_categories(root: Path = ROOT) -> list[Category]:
    return [c for c in list_categories(root) if c.delivery_mode == "bundled"]
