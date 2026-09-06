# popory_brief.categories — SKILL.md 디렉토리 스캔과 카테고리 메타 로드.
"""
services/brief/categories/{slug}/SKILL.md 디렉토리를 스캔해 활성 카테고리 목록을 반환.

API.
    list_categories(root=ROOT) -> list[Category]      # enabled 만
    load_category(slug, root=ROOT) -> Category        # 단일 (enabled 무시)
    standalone_categories(root=ROOT) -> list[Category]
    bundled_categories(root=ROOT) -> list[Category]

frontmatter 선택 필드 days. 콤마 구분 요일 토큰(mon~sun), 없거나 비면 매일 발행.
요일 게이트는 스케줄러(run_daily.sh 정규 실행)에서만 적용하고, load_category 직접
호출(--only 재시도·온디맨드)은 게이트 없이 그대로 실행된다.

frontmatter 선택 필드 seo_suffix. 포털·블로그 제목의 `|` 뒤 발행 꼬리 템플릿. 자리표시자
`{date_label}`(`9월 1주차`/`9월 5일`)·`{name}`. 없으면 `{date_label} {name} 브리핑`.
제목 형식 자체는 popory_brief.seo_title 참조 (키워드가 앞, 발행 정보가 뒤).

frontmatter 선택 필드 seo_body (기본 true). false 면 공통 SEO 규칙 중 본문 구조(소제목·표)
부분을 붙이지 않고 제목 규칙만 붙인다 — 헤딩·표를 일부러 쓰지 않는 메시지형 카테고리용.
"""
from __future__ import annotations
import datetime
from dataclasses import dataclass
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parent.parent / "categories"
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
VALID_MODES = {"standalone", "bundled", "portal_only"}
# 인덱스가 datetime.date.weekday()와 일치한다 (월=0 … 일=6).
VALID_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
REQUIRED = ("slug", "name", "delivery_mode", "subject_template", "sender_name", "enabled")
DEFAULT_SEO_SUFFIX = "{date_label} {name} 브리핑"


@dataclass(frozen=True)
class Category:
    slug: str
    name: str
    delivery_mode: str
    subject_template: str
    sender_name: str
    enabled: bool
    system_prompt: str
    days: tuple[str, ...] | None = None  # None = 매일
    seo_suffix: str = DEFAULT_SEO_SUFFIX
    seo_body: bool = True

    @property
    def area(self) -> str:
        return f"brief-{self.slug}"

    @property
    def weekly(self) -> bool:
        """주 1회 발행 카테고리인가. 제목 발행 라벨을 `M월 N주차` 로 쓸지 정한다."""
        return self.days is not None and len(self.days) == 1

    def runs_on(self, d: datetime.date) -> bool:
        return self.days is None or VALID_DAYS[d.weekday()] in self.days

    def title_suffix(self, d: datetime.date) -> str:
        """포털·블로그 제목의 `|` 뒤 발행 꼬리 (예. `9월 1주차 부동산 브리핑`)."""
        from popory_brief.seo_title import date_label
        return self.seo_suffix.format(date_label=date_label(d, weekly=self.weekly), name=self.name)

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
    days = _parse_days(meta.get("days"), path)
    seo_suffix = meta.get("seo_suffix")
    if seo_suffix is not None and not str(seo_suffix).strip():
        raise ValueError(f"{path}: seo_suffix 가 비어 있음")
    return Category(
        slug=str(meta["slug"]),
        name=str(meta["name"]),
        delivery_mode=str(meta["delivery_mode"]),
        subject_template=str(meta["subject_template"]),
        sender_name=str(meta["sender_name"]),
        enabled=bool(meta["enabled"]),
        system_prompt=body,
        days=days,
        seo_suffix=str(seo_suffix) if seo_suffix is not None else DEFAULT_SEO_SUFFIX,
        seo_body=bool(meta.get("seo_body", True)),
    )


def _parse_days(raw, path: Path) -> tuple[str, ...] | None:
    """days 필드 파싱. 콤마 구분 문자열(yaml 리스트도 허용) → 요일 토큰 tuple, 없거나 비면 None."""
    if raw is None:
        return None
    if isinstance(raw, str):
        tokens = [t.strip().lower() for t in raw.split(",") if t.strip()]
    elif isinstance(raw, list):
        tokens = [str(t).strip().lower() for t in raw if str(t).strip()]
    else:
        raise ValueError(f"{path}: invalid days {raw!r}")
    if not tokens:
        return None
    bad = [t for t in tokens if t not in VALID_DAYS]
    if bad:
        raise ValueError(f"{path}: invalid days tokens {bad!r} (허용: {','.join(VALID_DAYS)})")
    return tuple(dict.fromkeys(tokens))  # 중복 제거, 순서 유지


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
