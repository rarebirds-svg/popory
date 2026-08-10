# TTS 화자 A/B 비교 — 같은 원고를 여러 음성으로 합성해 나란히 듣는다.
# 실제 영상과 같은 조건으로 만든다(문장별 합성 → SENTENCE_GAP 무음 이어붙이기 → _deepen_voice).
#
# 실행: services/content 에서
#   source secrets/env.sh && .venv/bin/python scripts/compare_voices.py
#   .venv/bin/python scripts/compare_voices.py --list            # 계정에서 ko-KR 화자 목록 조회
#   .venv/bin/python scripts/compare_voices.py --voices male,charon,aoede
#
# 출력: ~/Downloads/popory_voice_ab/<timestamp>/ 에 MP3 + index.html(브라우저에서 바로 재생)
import argparse
import datetime
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from popory_content.tts import synthesize, _prep_text, _to_ssml
# 실제 영상 조립과 똑같은 조건으로 듣기 위해 video.py 헬퍼를 그대로 재사용한다.
from popory_content.video import (
    _split_sentences, _concat_audio_with_gaps, _deepen_voice, _duration,
    SENTENCE_GAP, VOICE_DEEPEN_SEMITONES,
)

VOICES_URL = "https://texttospeech.googleapis.com/v1/voices"
LANGUAGE = "ko-KR"

# 비교 후보. key = CLI 별칭, value = (표시명, 음성 ID).
# options.py VOICE 의 3종 + 사용자가 요청한 카론 + 나머지 Chirp3-HD 코어 화자.
CANDIDATES: dict[str, tuple[str, str]] = {
    # 현재 서비스가 쓰는 3종
    "male":    ("male · Neural2-C (현재 기본, 남)",      "ko-KR-Neural2-C"),
    "aoede":   ("female-calm · 아오에데 (여)",            "ko-KR-Chirp3-HD-Aoede"),
    "leda":    ("female-bright · 레다 (여)",              "ko-KR-Chirp3-HD-Leda"),
    # Chirp3-HD 코어 화자 — 남성
    "charon":  ("카론 Charon (남, 깊고 무게감)",          "ko-KR-Chirp3-HD-Charon"),
    "orus":    ("오루스 Orus (남, 낭독형)",               "ko-KR-Chirp3-HD-Orus"),
    "fenrir":  ("펜리르 Fenrir (남, 활기)",               "ko-KR-Chirp3-HD-Fenrir"),
    "puck":    ("퍽 Puck (남, 밝고 표현적)",              "ko-KR-Chirp3-HD-Puck"),
    # Chirp3-HD 코어 화자 — 여성
    "kore":    ("코레 Kore (여, 중립·정보전달)",          "ko-KR-Chirp3-HD-Kore"),
    "zephyr":  ("제피르 Zephyr (여, 맑고 단정)",          "ko-KR-Chirp3-HD-Zephyr"),
    # 구세대 비교군(무료 한도 버킷이 또 다름)
    "neural2a": ("Neural2-A (여, 구세대)",                "ko-KR-Neural2-A"),
    "wavenetc": ("WaveNet-C (남, 구세대)",                "ko-KR-Wavenet-C"),
}

# 기본 비교 대상 — 현행 남성 기본 vs 승격 후보들. 카론을 포함한다.
DEFAULT_PICKS = ["male", "charon", "orus", "aoede", "leda"]

# 포포리 책방 유튜브 내레이션 톤의 대표 원고(장면 1개, 6문장 ≈ 35초).
# 숫자·소수·퍼센트·인용을 일부러 섞어 tts.py 정규화 경로를 함께 검증한다.
SAMPLE = (
    "피터 린치는 월가에서 가장 성공한 펀드매니저로 꼽힙니다. "
    "그가 운용한 마젤란 펀드는 13년 동안 연평균 29.2%의 수익률을 기록했습니다. "
    "1977년 1,800만 달러였던 펀드 자산은 140억 달러까지 불어났습니다. "
    "하지만 그가 남긴 조언은 의외로 단순했습니다. "
    "자신이 아는 것에 투자하라, 그것이 전부였습니다. "
    "복잡한 수식이 아니라 일상의 관찰이 그의 무기였습니다."
)


def _require_key() -> str:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        print("error: GOOGLE_TTS_API_KEY 미설정 — 'source secrets/env.sh' 후 실행하세요.", file=sys.stderr)
        sys.exit(2)
    return key


def list_voices() -> None:
    """계정에서 실제로 쓸 수 있는 ko-KR 화자를 조회해 출력한다(문서보다 이게 정확)."""
    key = _require_key()
    try:
        resp = requests.get(VOICES_URL, params={"key": key, "languageCode": LANGUAGE}, timeout=30)
    except requests.RequestException as e:
        print(f"error: 조회 실패 — {e}", file=sys.stderr)
        sys.exit(1)
    if resp.status_code != 200:
        print(f"error: voices.list {resp.status_code} — {resp.text[:200]}", file=sys.stderr)
        sys.exit(1)
    voices = resp.json().get("voices", [])
    # 모델 계열(Chirp3-HD / Neural2 / Wavenet / Standard)별로 묶어 본다.
    groups: dict[str, list[tuple[str, str]]] = {}
    for v in voices:
        name = v.get("name", "")
        gender = {"MALE": "남", "FEMALE": "여"}.get(v.get("ssmlGender", ""), "?")
        family = name.split("-")[2] if name.count("-") >= 2 else "기타"
        groups.setdefault(family, []).append((name, gender))
    print(f"ko-KR 사용 가능 화자 {len(voices)}개\n")
    for family in sorted(groups, key=lambda f: (f != "Chirp3", f)):
        rows = sorted(groups[family])
        print(f"[{family}] {len(rows)}개")
        for name, gender in rows:
            speaker = name.split("-")[-1]
            print(f"  {gender}  {speaker:<18} {name}")
        print()


def synth_one(text: str, label: str, voice: str, out_dir: Path, index: int) -> dict | None:
    """한 음성으로 원고를 합성 — 실제 영상과 같이 문장별 합성 + 무음 갭 + (설정 시) 중저음 변형."""
    sentences = _split_sentences(text) or [text]
    work = out_dir / f"_work_{index}"
    work.mkdir(parents=True, exist_ok=True)
    segs: list[Path] = []
    billed = 0
    for j, sent in enumerate(sentences):
        billed += len(_to_ssml(_prep_text(sent)))  # SSML 태그까지 과금 대상이라 그대로 센다
        data = synthesize(sent, voice=voice)
        if not data:
            print(f"  ! {voice}: 문장 {j + 1} 합성 실패(키·권한·미지원 화자 확인)", file=sys.stderr)
            return None
        seg = work / f"{j}.mp3"
        seg.write_bytes(data)
        segs.append(_deepen_voice(seg))
    out = out_dir / f"{index:02d}_{voice}.mp3"
    _concat_audio_with_gaps(segs, SENTENCE_GAP, out)
    row = {"label": label, "voice": voice, "file": out.name,
           "seconds": _duration(out), "billed": billed}
    shutil.rmtree(work, ignore_errors=True)  # 문장별 중간 클립은 비교에 불필요 — 폴더를 깔끔히 유지
    return row


def build_index(text: str, rows: list[dict], out_dir: Path) -> None:
    deepen = (f"{VOICE_DEEPEN_SEMITONES}반음 적용" if VOICE_DEEPEN_SEMITONES > 0 else "미적용(기본)")
    cells = "".join(
        f"<tr><td>{r['label']}</td><td><code>{r['voice']}</code></td>"
        f"<td>{r['seconds']:.1f}초</td><td>{r['billed']:,}자</td>"
        f"<td><audio controls preload=none src='{r['file']}'></audio></td></tr>"
        for r in rows
    )
    html = (
        "<meta charset='utf-8'><title>포포리 TTS 화자 비교</title>"
        "<style>body{font-family:system-ui;margin:2rem;max-width:60rem}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.6rem;text-align:left}"
        "blockquote{background:#f6f6f6;padding:1rem;border-left:4px solid #999}</style>"
        "<h1>포포리 TTS 화자 비교</h1>"
        f"<p>실제 영상과 동일 조건: 문장별 합성 → 문장 사이 {SENTENCE_GAP}초 무음 → 중저음 변형 {deepen}.</p>"
        f"<blockquote>{text}</blockquote>"
        "<table><tr><th>화자</th><th>음성 ID</th><th>길이</th><th>과금 문자수</th><th>재생</th></tr>"
        f"{cells}</table>"
        "<p>과금 문자수는 SSML 태그 포함 기준. Neural2와 Chirp3-HD는 무료 한도(각 월 100만 자)가 분리돼 있다.</p>"
    )
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="포포리 TTS 화자 A/B 비교")
    ap.add_argument("--list", action="store_true", help="계정에서 ko-KR 화자 목록 조회 후 종료")
    ap.add_argument("--voices", help=f"비교할 별칭 쉼표 구분 (기본: {','.join(DEFAULT_PICKS)})")
    ap.add_argument("--all", action="store_true", help="CANDIDATES 전체 비교")
    ap.add_argument("--text", help="샘플 원고 직접 지정")
    args = ap.parse_args()

    if args.list:
        list_voices()
        return

    _require_key()
    text = args.text or SAMPLE
    if args.all:
        picks = list(CANDIDATES)
    elif args.voices:
        picks = [p.strip() for p in args.voices.split(",") if p.strip()]
    else:
        picks = DEFAULT_PICKS
    unknown = [p for p in picks if p not in CANDIDATES]
    if unknown:
        print(f"error: 모르는 별칭 {unknown} — 가능: {', '.join(CANDIDATES)}", file=sys.stderr)
        sys.exit(2)

    out_dir = Path.home() / "Downloads" / "popory_voice_ab" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, alias in enumerate(picks, start=1):
        label, voice = CANDIDATES[alias]
        print(f"[{i}/{len(picks)}] {label} — {voice}")
        row = synth_one(text, label, voice, out_dir, i)
        if row:
            rows.append(row)
            print(f"    → {row['file']} ({row['seconds']:.1f}초, 과금 {row['billed']:,}자)")
    if not rows:
        print("error: 합성된 음성이 없습니다.", file=sys.stderr)
        sys.exit(1)
    build_index(text, rows, out_dir)
    print(f"\n완료: open {out_dir}/index.html")


if __name__ == "__main__":
    main()
