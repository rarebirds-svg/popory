#!/usr/bin/env python3
"""기존 대본에 현재 TTS 전처리를 돌려, **읽기가 바뀐 문장만** 전/후로 보여 준다.

'전' 은 기억이 아니라 git 이력의 옛 tts.py 를 그대로 돌려서 얻는다(--before-rev, 기본 = 고유어 수사 PR(#67) 직전).
'후' 는 지금 작업 트리의 tts.py. 문장 분리는 실제 파이프라인의 video._split_sentences 를 쓴다 — 합성이 문장 단위라서다.

사용:
  python tools/tts_diff.py 대본_폴더/            # *.txt, *.md 를 모두 읽는다
  python tools/tts_diff.py a.txt b.txt
  cat 대본.txt | python tools/tts_diff.py -     # 표준입력
  python tools/tts_diff.py 대본.json             # ["대본1", ...] 또는 [{"draft": "..."}, ...]

대본 형식은 포털의 '전체 대본' 그대로면 된다: `[장면 제목]` 줄 다음에 내레이션. 대괄호 한 줄짜리 제목은 건너뛴다.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TTS_REL = "services/content/popory_content/tts.py"
DEFAULT_BEFORE_REV = "ba7f9e7^"        # 고유어 수사 PR(#67) 직전 — 모든 숫자를 한자어로 읽던 때


def load_tts_at(rev: str) -> types.ModuleType:
    """git 이력의 tts.py 를 별도 모듈로 불러온다(실제 파일은 건드리지 않는다)."""
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{TTS_REL}"],
                         capture_output=True, text=True, check=True).stdout
    mod = types.ModuleType(f"tts_at_{rev.replace('^', '_')}")
    mod.__file__ = f"<{rev}:{TTS_REL}>"
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


def read_texts(paths: list[str]) -> list[tuple[str, str]]:
    """(출처, 본문) 목록."""
    out: list[tuple[str, str]] = []
    for p in paths:
        if p == "-":
            out.append(("stdin", sys.stdin.read()))
            continue
        path = Path(p).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"경로가 없다: {p}")
        files = sorted(f for f in path.rglob("*") if f.suffix in (".txt", ".md", ".json")) if path.is_dir() else [path]
        for f in files:
            raw = f.read_text(encoding="utf-8")
            if f.suffix == ".json":
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
                for i, it in enumerate(items):
                    text = it if isinstance(it, str) else (it.get("draft") or it.get("script") or "")
                    out.append((f"{f.name}#{i + 1}", str(text)))
            else:
                out.append((f.name, raw))
    return out


def narration_lines(text: str) -> list[str]:
    """대본에서 내레이션 줄만. `[장면 제목]` 한 줄짜리와 빈 줄은 건너뛴다."""
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or (s.startswith("[") and s.endswith("]")):
            continue
        lines.append(s)
    return lines


def changed_sentences(texts: list[tuple[str, str]], split, before, after) -> tuple[int, list[dict]]:
    """(전체 문장 수, 바뀐 문장 목록). before/after 는 문장 → 읽는 형태 함수."""
    total, changed = 0, []
    for source, text in texts:
        for ln in narration_lines(text):
            for sent in split(ln) or [ln]:
                total += 1
                b, a = before(sent), after(sent)
                if b != a:
                    changed.append({"source": source, "text": sent, "before": b, "after": a})
    return total, changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="대본 파일/폴더, 또는 - (표준입력)")
    ap.add_argument("--before-rev", default=DEFAULT_BEFORE_REV, help=f"'전' 으로 쓸 git 리비전 (기본 {DEFAULT_BEFORE_REV})")
    args = ap.parse_args(argv)

    sys.path.insert(0, str(ROOT / "services" / "content"))
    from popory_content import tts as tts_now
    from popory_content.video import _split_sentences

    try:
        tts_old = load_tts_at(args.before_rev)
    except subprocess.CalledProcessError as e:
        print(f"'전' 리비전을 읽지 못했다: {args.before_rev} ({(e.stderr or '').strip()[:120]}) — git fetch 후 다시", file=sys.stderr)
        return 2

    try:
        texts = read_texts(args.paths)
    except FileNotFoundError as e:
        print(f"{e}\n(예시 경로가 아니라 대본이 실제로 들어 있는 폴더·파일 경로를 넣는다. 확인: ls <경로>)", file=sys.stderr)
        return 2
    if not texts:
        print("읽을 대본이 없다 — 폴더 안에 .txt / .md / .json 파일이 있어야 한다.", file=sys.stderr)
        return 2
    total, changed = changed_sentences(texts, _split_sentences, tts_old.spoken_text, tts_now.spoken_text)
    print(f"대본 {len(texts)}건 · 문장 {total}개 중 읽기가 바뀐 문장 {len(changed)}개 (전: {args.before_rev})\n")
    for c in changed:
        print(f"[{c['source']}]")
        print(f"  원문: {c['text']}")
        print(f"  전:   {c['before']}")
        print(f"  후:   {c['after']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
