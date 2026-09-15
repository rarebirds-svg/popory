# Gemini 키·모델·검색 grounding 이 실제로 동작하는지 확인하는 점검 CLI (실호출 1회, 토큰 소량).
"""사용법.
    .venv/bin/python check_gemini.py [--model gemini-3.8-flash]

브리핑을 돌리기 전에 (1) 키가 읽히는지 (2) 모델 id 가 맞는지 (3) Google Search grounding
도구 이름이 맞는지를 나눠서 본다 — 셋 중 하나가 틀려도 브리핑 로그에는 "생성 실패" 한 줄만
남아 원인을 가려내기 어렵다. 키는 앞뒤 몇 글자만 마스킹해 출력하므로 터미널에 노출되지 않는다.
"""
from __future__ import annotations

import argparse
import sys

from popory_brief import gemini_client

DEFAULT_MODEL = "gemini-3.8-flash"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"확인할 모델 id (기본 {DEFAULT_MODEL})")
    args = p.parse_args()

    try:
        key = gemini_client.api_key()
    except gemini_client.GeminiError as e:
        print(f"[1/3] 키 실패 — {e}")
        print("      env GEMINI_API_KEY 또는 secrets/gemini_api_key (키 값만 한 줄) 를 확인하세요.")
        return e.exit_code
    print(f"[1/3] 키 읽힘 — {key[:6]}...{key[-4:]} (길이 {len(key)})")

    try:
        out, sources = gemini_client.generate_with_sources(
            system_prompt="한국어로 한 줄만 답한다.",
            user_msg="오늘 한국 부동산 관련 뉴스가 있으면 기사 제목 하나만 적어라.",
            model=args.model,
            timeout_seconds=120,
        )
    except gemini_client.GeminiError as e:
        print(f"[2/3] 호출 실패 — {e}")
        print(f"      모델 id 를 지적하면 --model 로 바꿔 보세요 (지금: {args.model}).")
        print(f"      검색 도구 이름을 지적하면 BRIEF_GEMINI_SEARCH_TOOL 로 교정할 수 있습니다 "
              f"(지금: {gemini_client.SEARCH_TOOL}).")
        return e.exit_code

    print(f"[2/3] 호출·검색 정상 — 모델 {args.model}, 도구 {gemini_client.SEARCH_TOOL}, 응답 {len(out)}자")
    print(f"      응답 앞부분: {out.strip()[:120]}")

    # 근거 URL 은 본문에 적힌 출처와 별개다 — 본문 URL 은 모델이 만든 문자열이라 404 가 섞인다.
    # 이 목록이 인용 검증의 기준이 되므로, 실측 형태를 볼 수 있게 그대로 출력한다.
    print(f"[3/3] grounding 근거 URL {len(sources)}개")
    for i, uri in enumerate(sources[:5], start=1):
        print(f"      {i}) {uri[:140]}")
    if not sources:
        print("      (없음 — 이 응답은 검색 근거 없이 생성됐다는 뜻이다)")

    print("모두 정상입니다. 카테고리 시범을 돌려 보세요:")
    print(f"      .venv/bin/python generate_brief.py --category naver --model {args.model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
