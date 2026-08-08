# flux-1-schnell vs FLUX.2 klein 9B A/B 비교 — 대표 프롬프트를 두 모델로 생성해 나란히 저장.
# 워커와 같은 자격(POPORY_CONTENT_KEY_FILE, POPORY_PORTAL_API_BASE)으로 portal ai-image를 호출한다.
# 실행: services/content 에서  .venv/bin/python scripts/compare_image_models.py
# 출력: ~/Downloads/popory_image_ab/<timestamp>/ 에 PNG + index.html(좌우 비교)
import datetime
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError

AREA = "content-worker"
AI_IMAGE_PATH = "/api/content/ai-image"
MODELS = ("schnell", "klein")

# 포포리 영상에서 실제로 나오는 유형별 대표 프롬프트(스타일 키워드 photorealistic, cinematic 동일).
PROMPTS = [
    # 인물 — schnell의 약점(얼굴·손 기형) 확인용
    "A middle-aged Korean man reading a book by a window in a cozy study, warm afternoon light, "
    "relaxed natural expression, photorealistic, cinematic",
    # 실내 정경 — 책방 브랜드 무드
    "A quiet Korean bookstore interior at dusk, warm lamplight over wooden bookshelves, "
    "empty reading chair, photorealistic, cinematic",
    # 투자·경제 은유 — 데일리 큐레이션 최다 주제
    "A rising stack of coins beside an old ledger on a wooden desk, soft morning light, "
    "shallow depth of field, photorealistic, cinematic",
    # 자연 풍경 — 시·에세이 주제
    "A misty mountain path at sunrise with autumn foliage, a distant lone walker, "
    "photorealistic, cinematic",
]


def _make_client() -> PortalClient:
    key_file = os.environ.get("POPORY_CONTENT_KEY_FILE")
    base = os.environ.get("POPORY_PORTAL_API_BASE")
    if not key_file or not Path(key_file).exists():
        print(f"error: POPORY_CONTENT_KEY_FILE 미설정/없음: {key_file}", file=sys.stderr)
        sys.exit(2)
    if not base:
        print("error: POPORY_PORTAL_API_BASE 미설정", file=sys.stderr)
        sys.exit(2)
    material = KeyMaterial.load(Path(key_file))
    return PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area=AREA, ttl_seconds=300),
    )


def main() -> None:
    client = _make_client()
    out_dir = Path.home() / "Downloads" / "popory_image_ab" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, prompt in enumerate(PROMPTS, start=1):
        cells = []
        for model in MODELS:
            name = f"p{i}_{model}.png"
            t0 = datetime.datetime.now()
            try:
                png = client.post_for_bytes(AI_IMAGE_PATH, json={"prompt": prompt, "model": model})
            except PortalError as e:
                print(f"[{i}/{len(PROMPTS)}] {model}: 실패 — {e}", file=sys.stderr)
                cells.append(f"<td>실패: {e}</td>")
                continue
            secs = (datetime.datetime.now() - t0).total_seconds()
            (out_dir / name).write_bytes(png)
            print(f"[{i}/{len(PROMPTS)}] {model}: {name} ({len(png)//1024}KB, {secs:.1f}s)")
            cells.append(f'<td><img src="{name}" width="480"><br>{model} · {secs:.1f}s</td>')
        rows.append(f"<tr><td style='max-width:200px'>{prompt}</td>{''.join(cells)}</tr>")
    html = (
        "<meta charset='utf-8'><h1>flux-1-schnell vs FLUX.2 klein 9B</h1>"
        "<table border=1 cellpadding=8><tr><th>prompt</th><th>schnell</th><th>klein</th></tr>"
        + "".join(rows) + "</table>"
    )
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"완료: open {out_dir}/index.html")


if __name__ == "__main__":
    main()
