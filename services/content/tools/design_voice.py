#!/usr/bin/env python3
# 운영 남성 음성(Gemini Voice design 설계 음성)을 같은 페르소나로 다시 만들고, 저장된 설계 음성 목록을 보는 도구.
"""운영 남성 음성(options.VOICE["male"])인 Gemini 설계 음성을 같은 페르소나로 다시 만든다.

배경 — 프리셋 화자(Iapetus)는 합성할 때마다 목소리를 새로 만들어 챕터마다 목소리가 바뀌었다. Voice design 으로
만든 설계 음성은 목소리를 저장해 두고 ID(voice_…)로 부른다(2026-11-08 voice_s8vzho2m0lq6). 저장 음성은 만든 뒤
1년이 지나면 만료되고 API 키의 Google 프로젝트에 묶인다. 워커가 만료 30일 전부터 gemini_voice_expiry_failed 를
남기면 이 도구로 새로 만들고 options.py 의 VOICE·DESIGNED_VOICE_EXPIRES 를 바꾼다.

같은 페르소나로 다시 만들어도 목소리가 달라질 수 있다 — 바꾸기 전에 tools/voice_ab.py 로 다시 잰다.

사용(맥미니, services/content 에서)
  .venv/bin/python tools/design_voice.py                                   # 보낼 요청 본문만 보고 끝(요청 없음)
  (source secrets/env.sh; .venv/bin/python tools/design_voice.py --yes)    # 실제로 만든다(요금 약 $0.01)
  (source secrets/env.sh; .venv/bin/python tools/design_voice.py --list)   # 저장된 ko-KR 설계 음성 목록

--yes 는 새 voice ID·만료 시각을 찍고, 응답의 미리듣기(sample_audio, WAV)를 ~/Downloads/popory_voice_design/<id>.wav 로
저장한 뒤 다음 조치(다시 재기·options.py 두 값 교체·워커 재시작)를 안내한다.
"""
import argparse
import base64
import datetime
import json
import os
import sys
from pathlib import Path

import requests

API_URL = "https://generativelanguage.googleapis.com/v1beta/voices"
MODEL = "gemini-3.8-flash-tts"
# 2026-11-08 voice_s8vzho2m0lq6 를 만든 페르소나 그대로. 화자의 나이·성별·말투는 여기서 정하고, 합성 때 연출 지시
# (gemini_tts.DEFAULT_STYLE)는 짧게 둔다.
PERSONA = ("A calm, warm Korean man in his forties who narrates book reviews to a single listener. "
           "Natural conversational pace, gentle and trustworthy, never like a news announcer.")
DISPLAY_NAME = "popory-narrator-v1"
PREVIEW_DIR = Path.home() / "Downloads" / "popory_voice_design"
TIMEOUT_SECONDS = 120


def build_request(persona: str = PERSONA, display_name: str = DISPLAY_NAME) -> dict:
    """설계 음성 생성 요청 본문. store=True 여야 저장돼 ID 로 다시 부를 수 있다."""
    return {"store": True, "voice": {"model": MODEL, "type": "prompted", "display_name": display_name,
                                     "gender": "male", "language_code": "ko-KR", "prompted": {"input": persona}}}


def _http_failed(resp) -> bool:
    """200 이 아니면 상태 코드와 본문 앞 300자를 찍는다."""
    if resp.status_code == 200:
        return False
    print(f"HTTP {resp.status_code} — {resp.text[:300]}", file=sys.stderr)
    return True


def _voices(data) -> list:
    """목록 응답에서 음성 목록을 꺼낸다. 최상위 키 이름은 확인되지 않아 voices 를 먼저 보고, 없으면 리스트인 값을 쓴다."""
    if isinstance(data, list):
        return data
    if isinstance(data.get("voices"), list):
        return data["voices"]
    return next((v for v in data.values() if isinstance(v, list)), [])


def list_voices(key: str) -> int:
    resp = requests.get(API_URL, params={"type": "prompted", "language_code": "ko-KR"},
                        headers={"x-goog-api-key": key}, timeout=TIMEOUT_SECONDS)
    if _http_failed(resp):
        return 1
    voices = _voices(resp.json())
    for v in voices:
        print(f"{v.get('id')}  {v.get('display_name')}  만료 {v.get('expire_time')}")
    if not voices:
        print("저장된 ko-KR 설계 음성이 없다.")
    return 0


def create(key: str) -> int:
    try:
        resp = requests.post(API_URL, headers={"x-goog-api-key": key}, json=build_request(), timeout=TIMEOUT_SECONDS)
    except requests.RequestException as e:
        print(f"요청 실패 — {e}\n서버에서는 만들어졌을 수 있다. 다시 만들기 전에 --list 로 확인한다.", file=sys.stderr)
        return 1
    if _http_failed(resp):
        return 1
    data = resp.json()
    vid, expire = data["id"], data.get("expire_time", "")
    print(f"만든 음성 {vid} · 만료 {expire}")
    audio = (data.get("sample_audio") or {}).get("data")
    if audio:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        preview = PREVIEW_DIR / f"{vid}.wav"
        preview.write_bytes(base64.b64decode(audio))
        print(f"미리듣기 {preview}")
    else:
        print("응답에 미리듣기(sample_audio)가 없다.")
    d = datetime.date.fromisoformat(expire[:10])
    print(f"""
다음 조치 — 같은 페르소나여도 목소리가 다를 수 있다. 바꾸기 전에 다시 잰다.
  1. 미리듣기를 듣는다.
  2. (source secrets/env.sh; .venv/bin/python tools/voice_ab.py --voice {MODEL}/{vid} --yes)
     장면 사이 폭·보정량이 지금 음성의 기록(SKILL.md TTS 절)보다 나쁘지 않은지 본다.
  3. popory_content/options.py 의 두 값을 함께 바꾼다.
       VOICE["male"] = "{MODEL}/{vid}"
       DESIGNED_VOICE_EXPIRES = {{"{vid}": datetime.date({d.year}, {d.month}, {d.day})}}
  4. 머지 후 맥미니에서 git pull → 진행 중 작업이 없을 때 launchctl kill 9 gui/$(id -u)/com.popory.content-worker""")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="운영 남성 음성(Gemini 설계 음성)을 같은 페르소나로 다시 만든다")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--yes", action="store_true", help="실제로 만든다(요금 약 $0.01, 없으면 요청 본문만 보여 준다)")
    mode.add_argument("--list", action="store_true", help="저장된 ko-KR 설계 음성의 ID·이름·만료 시각")
    args = ap.parse_args(argv)
    if not (args.yes or args.list):
        print(f"POST {API_URL}\n{json.dumps(build_request(), ensure_ascii=False, indent=1)}")
        print("\n요청하지 않았다. 실제로 만들려면 --yes 를 붙인다(요금 약 $0.01, GEMINI_API_KEY 필요 — source secrets/env.sh).")
        return 0
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY 미설정 — (source secrets/env.sh; …) 로 실행한다.", file=sys.stderr)
        return 2
    return list_voices(key) if args.list else create(key)


if __name__ == "__main__":
    sys.exit(main())
