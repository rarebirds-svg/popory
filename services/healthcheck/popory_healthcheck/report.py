# 점검 결과를 공용 보고 계약의 5영역으로 접는다 — 문자열 조립은 공용 포맷터가 한다.
_RANK = {"ok": 0, "warn": 1, "fail": 2}

# 점검명 → 영역. 새 점검을 추가하면 여기에도 등록해야 한다(미등록은 예외로 막는다).
_AREA_OF = {
    "포털": "service",
    "API": "service",
    "Claude인증": "jobs",
    "브리핑": "jobs",
    "브리핑잡": "jobs",
    "워커데몬": "jobs",
    "이미지데몬": "jobs",
    "콘텐츠루틴": "jobs",
    "자원한도": "anomaly",
    "워커로그": "anomaly",
}
# 전부 ok일 때 쓰는 짧은 요약. 개별 메시지를 늘어놓으면 40자를 넘고 훑기 어려워진다.
_OK_SUMMARY = {
    "service": "포털·API 정상",
    "jobs": "인증·브리핑·데몬·루틴 정상",
    "anomaly": "한도·로그 이상 없음",
}
_SECTION_ORDER = ("service", "jobs", "deploy", "anomaly", "approval")


def overall(results: list[tuple[str, str, str]]) -> str:
    worst = "ok"
    for _, status, _msg in results:
        if _RANK[status] > _RANK[worst]:
            worst = status
    return worst


def fold_sections(results: list[tuple[str, str, str]]) -> dict:
    """9개 점검을 5영역으로 접는다. 영역 상태는 소속 항목의 최악값이다."""
    buckets: dict[str, list[tuple[str, str, str]]] = {"service": [], "jobs": [], "anomaly": []}
    for name, status, msg in results:
        area = _AREA_OF.get(name)
        if area is None:
            raise ValueError(f"미등록 점검명: {name} — _AREA_OF에 영역을 추가하라")
        buckets[area].append((name, status, msg))

    sections = {}
    for area, items in buckets.items():
        worst = "ok"
        worst_msg = ""
        for _name, status, msg in items:
            if _RANK[status] > _RANK[worst]:
                worst = status
                worst_msg = msg
        sections[area] = {
            "status": worst,
            "text": worst_msg if worst != "ok" else _OK_SUMMARY[area],
        }

    # popory는 배포 갭·승인 절차가 없다. 자리는 비워 두되 지우지 않는다.
    sections["deploy"] = {"status": "na", "text": "해당 없음"}
    sections["approval"] = {"status": "na", "text": "없음"}
    return {key: sections[key] for key in _SECTION_ORDER}


def state_signature(results: list[tuple[str, str, str]]) -> dict:
    return {name: status for name, status, _ in results}
