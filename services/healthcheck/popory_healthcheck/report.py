# 점검 결과 → 텔레그램 메시지 조립 + 모드별 발송 정책·중복 억제.
_EMOJI = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
_RANK = {"ok": 0, "warn": 1, "fail": 2}


def overall(results: list[tuple[str, str, str]]) -> str:
    worst = "ok"
    for _, status, _msg in results:
        if _RANK[status] > _RANK[worst]:
            worst = status
    return worst


def format_report(results: list[tuple[str, str, str]], header: str) -> str:
    lines = [f"[popory 점검] {header} — 전체 {_EMOJI[overall(results)]}"]
    for name, status, msg in results:
        lines.append(f"{_EMOJI[status]} {name} — {msg}")
    return "\n".join(lines)


def state_signature(results: list[tuple[str, str, str]]) -> dict:
    return {name: status for name, status, _ in results}


def _has_anomaly(results) -> bool:
    return any(status in ("warn", "fail") for _, status, _ in results)


def should_send(mode: str, results, prev: dict | None) -> bool:
    if mode == "am":
        return True
    # pm — 이상 있을 때만, 직전과 완전 동일하면 억제.
    if not _has_anomaly(results):
        return False
    if prev is not None and state_signature(results) == prev:
        return False
    return True
