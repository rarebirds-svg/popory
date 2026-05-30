# bundled 카테고리들을 수신자별 본문으로 묶어 JSONL로 출력하는 헬퍼.
"""
사용법.
    python build_bundles.py --slugs s1,s2,s3 --date 2026-05-31 [--gen-failed s4,s5]

흐름.
    각 bundled slug 별 fetch_subscribers → 본문 파일 읽기 → 수신자 union → 수신자별로
    구독한 bundled 카테고리만 ## name 헤더로 합쳐 /tmp/bundle_{email_hash}_{date}.md 작성.

stdout JSONL (수신자 1명당 1줄).
    {"email":"...", "body_file":"/tmp/bundle_..."}

stderr는 사람 읽기용 로그. 실패한 수신자는 skip + stderr 기록 후 다음 진행.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from popory_brief.categories import load_category

BRIEF_DIR = Path(__file__).resolve().parent


def fetch_subscribers(slug: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, str(BRIEF_DIR / "fetch_subscribers.py"), "--area", f"brief-{slug}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(
            f"fetch_subscribers --area brief-{slug} exit {result.returncode}: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"fetch_subscribers --area brief-{slug} bad json: {e}", file=sys.stderr)
        return []
    return [s["email"] for s in data.get("subscribers", [])]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--slugs", required=True, help="comma-separated bundled category slugs")
    p.add_argument("--date", required=True)
    p.add_argument("--gen-failed", default="", help="comma-separated slugs that failed generate")
    args = p.parse_args()

    slugs = [s for s in args.slugs.split(",") if s]
    failed = {s for s in args.gen_failed.split(",") if s}

    subs_by_slug: dict[str, set[str]] = {}
    body_by_slug: dict[str, str] = {}
    name_by_slug: dict[str, str] = {}

    for slug in slugs:
        try:
            cat = load_category(slug)
        except KeyError as e:
            print(f"skip slug={slug}: {e}", file=sys.stderr)
            continue
        name_by_slug[slug] = cat.name
        if slug in failed:
            continue
        subs_by_slug[slug] = set(fetch_subscribers(slug))
        body_path = Path(f"/tmp/brief_{slug}_{args.date}.md")
        if not body_path.exists():
            print(f"skip slug={slug}: body file missing {body_path}", file=sys.stderr)
            failed.add(slug)
            continue
        body_by_slug[slug] = body_path.read_text(encoding="utf-8")

    all_emails = sorted({e for subs in subs_by_slug.values() for e in subs})

    for email in all_emails:
        sections = []
        for slug in slugs:
            if slug not in body_by_slug:
                continue
            if email not in subs_by_slug.get(slug, set()):
                continue
            sections.append(f"## {name_by_slug[slug]}\n\n{body_by_slug[slug]}")
        if not sections:
            continue
        bundle_md = "\n\n".join(sections)
        if failed:
            failed_names = ", ".join(sorted(name_by_slug.get(s, s) for s in failed))
            bundle_md += f"\n\n---\n\n> 일부 카테고리 본문 생성 실패: {failed_names}\n"
        email_hash = hashlib.sha1(email.encode()).hexdigest()[:12]
        body_path = Path(f"/tmp/bundle_{email_hash}_{args.date}.md")
        body_path.write_text(bundle_md, encoding="utf-8")
        print(json.dumps({"email": email, "body_file": str(body_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
