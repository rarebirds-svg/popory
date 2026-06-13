# 세션 한도로 실패한 브리프 항목을 pending json에 기록한다(retry_count 보존·증가)
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--reset-at", type=int, required=True)
    p.add_argument("--categories", default="", help="csv 슬러그")
    p.add_argument("--custom", default="", help="csv 커스텀 주제 id")
    p.add_argument("--increment", action="store_true", help="retry_count를 +1")
    args = p.parse_args()

    path = Path(args.file)
    prev = 0
    if path.exists():
        try:
            prev = int(json.loads(path.read_text(encoding="utf-8")).get("retry_count", 0))
        except (ValueError, OSError):
            prev = 0
    retry_count = prev + 1 if args.increment else prev

    payload = {
        "date": args.date,
        "reset_at": args.reset_at,
        "categories": [c for c in args.categories.split(",") if c],
        "custom_topics": [c for c in args.custom.split(",") if c],
        "retry_count": retry_count,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"pending: cats={payload['categories']} custom={payload['custom_topics']} "
        f"reset_at={args.reset_at} retry_count={retry_count}"
    )


if __name__ == "__main__":
    main()
