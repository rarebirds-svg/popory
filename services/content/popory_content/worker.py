# 포털 큐에서 컨텐츠 작업을 claim → claude 생성 → 결과 회신. __main__ 은 무한 poll 루프.
import datetime
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from popory_content.generate import generate, GenerateError
from popory_content.video_prompt import build_shorts_system_prompt, build_shorts_user_message
from popory_content.video import make_video, VideoError
from popory_content.youtube_upload import upload
from popory_content.options import parse_options, parse_shorts_options, SCENE_COUNT, SHORT_SCENE_COUNT, VOICE, STYLE
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log
from popory_content.instagram_image_prompt import build_carousel_system_prompt, build_carousel_user_message
from popory_content.instagram_image_contract import parse_carousel
from popory_content.instagram_image_render import render_carousel
from popory_content.instagram_upload import upload_reels, upload_carousel, InstagramUploadError

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
WORKER_AREA = "content-worker"


def _generate_carousel(*, topic: str, sources: list, style_samples: list, job_id: str, slide_count: int):
    """Claude CLI로 캐러셀 슬라이드 배열 생성."""
    from popory_content.generate import run_claude_cli
    sp = build_carousel_system_prompt(style_samples, slide_count=slide_count)
    um = build_carousel_user_message(topic, sources)
    return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_carousel, job_id=job_id)
POLL_INTERVAL_SECONDS = 20
# 서비스 JWT 수명. 60초는 시계 오차·느린 요청에 취약(일시 401 관측) → 여유 상향.
TOKEN_TTL_SECONDS = 300


def run_once(client) -> bool:
    """큐에서 한 건 처리. 처리했으면 True, 큐가 비었으면 False."""
    data = client.post("/api/content/jobs/claim", json=None)
    if not data:
        return False
    job = data["job"]
    sources = data.get("sources", [])
    samples = data.get("style_samples", [])
    job_id = job["id"]
    platform = job.get("platform", "naver-blog")
    try:
        if platform == "youtube":
            opts = parse_options(job.get("params_json"))
            mp4, scenes, meta, img_missing, img_total = make_video(
                topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
                image_fetcher=lambda p: _safe_image(client, p, job_id),
                scene_count=SCENE_COUNT[opts["length"]],
                image_style_kw=STYLE[opts["image_style"]],
                voice=VOICE[opts["voice"]],
            )
            client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
            script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
            _finalize_video(client, job_id, script, meta, img_missing, img_total)
        elif platform == "shorts":
            opts = parse_shorts_options(job.get("params_json"))
            mp4, scenes, meta, img_missing, img_total = make_video(
                topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
                image_fetcher=lambda p: _safe_image(client, p, job_id),
                scene_count=SHORT_SCENE_COUNT[opts["length"]],
                image_style_kw=STYLE[opts["image_style"]],
                voice=VOICE[opts["voice"]],
                portrait=True,
                system_prompt_builder=build_shorts_system_prompt,
                user_msg_builder=build_shorts_user_message,
            )
            client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
            script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
            _finalize_video(client, job_id, script, meta, img_missing, img_total)
        elif platform == "instagram-image":
            import json as _json
            params: dict = {}
            if job.get("params_json"):
                try:
                    params = _json.loads(job["params_json"])
                except Exception:
                    params = {}
            slide_count = int(params.get("slide_count", 7))
            slide_count = max(3, min(10, slide_count))
            slides, meta = _generate_carousel(
                topic=job["topic"], sources=sources, style_samples=samples,
                job_id=job_id, slide_count=slide_count,
            )
            images = render_carousel(
                slides, image_fetcher=lambda p: _safe_image(client, p)
            )
            client.put_carousel(job_id, images)
            caption = meta.get("caption", "")
            _report(client, job_id, {"status": "review", "draft": caption, "meta": meta}, "review")
        else:
            draft, meta = generate(topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id)
            _report(client, job_id, {"status": "review", "draft": draft, "meta": meta}, "review")
    except Exception as e:  # noqa: BLE001 — 생성 실패는 failed 로 회신
        _report(client, job_id, {"status": "failed", "error": str(e)[:2000]}, "failed")
    return True


def _report(client, job_id: str, body: dict, status_label: str) -> None:
    """결과 회신. 회신 자체가 실패해도 poll 루프를 죽이지 않는다(작업은 running 으로 남음)."""
    try:
        client.patch(f"/api/content/jobs/{job_id}/result", json=body)
        append_log(LOGS_DIR, {"worker": "content", "status": status_label, "job": job_id})
    except Exception as e:  # noqa: BLE001 — 회신 실패는 로그만 남긴다
        append_log(LOGS_DIR, {"worker": "content", "status": "report_failed", "job": job_id, "error": str(e)[:300]})


IMAGE_MAX_ATTEMPTS = 3
IMAGE_BACKOFF = [2, 5]
IMAGE_FAIL_RATIO = 0.5
IMAGEGEN_URL = os.environ.get("POPORY_IMAGEGEN_URL", "http://localhost:8765/generate")
# 로컬 fp32 SDXL/SD 생성은 맥미니 16GB 메모리 압박에서 장면당 ~110초가 걸린다.
# 120초는 빠듯해 종종 read timeout → 재시도 낭비 → 단색 폴백을 유발했다. 여유 상향.
IMAGE_TIMEOUT_SECONDS = int(os.environ.get("POPORY_IMAGEGEN_TIMEOUT", "300"))
# 1순위 = Cloudflare flux-schnell(무료 ~10k neurons/일). 한도 소진(4006)이면 로컬 RealVisXL 폴백.
USE_CF_IMAGE = os.environ.get("POPORY_USE_CF_IMAGE", "1") != "0"
CF_AI_IMAGE_PATH = "/api/content/ai-image"
CF_QUOTA_FILE = LOGS_DIR / "cf_quota.json"


def _verify_image(data: bytes) -> None:
    """이미지 응답이 디코드 가능한 완전한 이미지인지 확인한다. 연결 끊김으로 잘린
    바이트(BrokenPipe)면 raise → 재시도·image_failed 로깅으로 이어져 조용한 단색 폴백을 막는다."""
    if not data:
        raise RuntimeError("empty image response")
    Image.open(BytesIO(data)).load()  # 잘린/깨진 이미지면 여기서 예외


def _utc_today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _cf_exhausted_today() -> bool:
    """CF 무료 한도(4006)가 오늘(UTC) 소진됐는지. 다음 UTC 날 자동 리셋."""
    try:
        return json.loads(CF_QUOTA_FILE.read_text()).get("exhausted_date") == _utc_today()
    except Exception:  # noqa: BLE001 — 파일 없음/깨짐이면 미소진으로 간주
        return False


def _mark_cf_exhausted() -> None:
    try:
        CF_QUOTA_FILE.write_text(json.dumps({"exhausted_date": _utc_today()}))
    except Exception:  # noqa: BLE001
        pass


def _try_cloudflare(client, prompt: str) -> bytes | None:
    """CF flux-schnell로 1장. 한도(4006/neurons)면 그날 소진 표시 후 None(→로컬 폴백). 그 외 실패도 None."""
    try:
        content = client.post_for_bytes(CF_AI_IMAGE_PATH, json={"prompt": prompt})
        _verify_image(content)
        return content
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "4006" in msg or "neuron" in msg.lower():
            _mark_cf_exhausted()
        return None


def _safe_image(client, prompt: str, job_id: str = "?"):
    """배경 1장 생성. 1순위 CF flux-schnell(무료), 한도 소진·실패 시 로컬 RealVisXL 폴백.
    깨진 응답은 검증으로 걸러 재시도, 최종 실패만 image_failed 로그+None."""
    if USE_CF_IMAGE and client is not None and not _cf_exhausted_today():
        img = _try_cloudflare(client, prompt)
        if img is not None:
            return img
    last = ""
    for attempt in range(1, IMAGE_MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(IMAGEGEN_URL, json={"prompt": prompt}, timeout=IMAGE_TIMEOUT_SECONDS)
            if resp.status_code >= 400:
                raise RuntimeError(f"imagegen {resp.status_code}: {resp.text[:200]}")
            content = resp.content
            _verify_image(content)  # 잘린/깨진 바이트면 raise → 재시도
            return content
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            if attempt < IMAGE_MAX_ATTEMPTS:
                time.sleep(IMAGE_BACKOFF[attempt - 1])
    append_log(LOGS_DIR, {"worker": "content", "status": "image_failed", "job": job_id, "error": last})
    return None


def _finalize_video(client, job_id, script, meta, img_missing, img_total):
    """누락 이미지 비율로 status 결정. 대부분 실패면 failed, 일부면 review+경고."""
    if img_total > 0 and img_missing / img_total >= IMAGE_FAIL_RATIO:
        _report(client, job_id, {
            "status": "failed", "draft": script, "meta": meta,
            "error": f"배경 이미지 생성 실패 ({img_missing}/{img_total} 장면) — 재생성 필요",
        }, "failed")
    else:
        if img_missing:
            meta = {**meta, "images_missing": img_missing, "images_total": img_total}
        _report(client, job_id, {"status": "review", "draft": script, "meta": meta}, "review")


def _issue_media_token(client, r2_key: str) -> str:
    """R2 키에 대한 임시 공개 URL 발급."""
    data = client.post("/api/content/media-token", json={"r2_key": r2_key})
    return data["url"]


def _build_client() -> PortalClient:
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
        token_provider=lambda: sign_for_portal(material, area=WORKER_AREA, ttl_seconds=TOKEN_TTL_SECONDS),
    )


def run_upload_once(client) -> bool:
    """업로드 요청 1건 처리. 처리했으면 True."""
    data = client.post("/api/content/youtube/claim-upload", json=None)
    if not data:
        return False
    job_id = data["job_id"]
    try:
        mp4 = client.get_bytes(f"/api/content/jobs/{job_id}/video")
        video_id = upload(data["access_token"], mp4, data.get("title", "popory 영상"), data.get("description", ""), data.get("tags", []), privacy=data.get("privacy", "public"))
        client.patch(f"/api/content/jobs/{job_id}/youtube-result", json={"status": "done", "video_id": video_id})
        append_log(LOGS_DIR, {"worker": "content", "status": "uploaded", "job": job_id, "video": video_id})
    except Exception as e:  # noqa: BLE001 — 업로드 실패는 result 에 기록하고 계속
        try:
            client.patch(f"/api/content/jobs/{job_id}/youtube-result", json={"status": "failed", "error": str(e)[:500]})
        except Exception:  # noqa: BLE001
            pass
        append_log(LOGS_DIR, {"worker": "content", "status": "upload_failed", "job": job_id, "error": str(e)[:300]})
    return True


def run_instagram_upload_once(client) -> bool:
    """Instagram 업로드 요청 1건 처리. 처리했으면 True."""
    data = client.post("/api/content/instagram/claim-upload", json=None)
    if not data:
        return False
    job_id = data["job_id"]
    platform = data["platform"]
    ig_user_id = data["ig_user_id"]
    access_token = data["access_token"]
    caption = data.get("caption", "")
    try:
        if platform == "shorts":
            video_url = _issue_media_token(client, f"content/video/{job_id}.mp4")
            media_id = upload_reels(ig_user_id, access_token, video_url, caption)
        elif platform == "instagram-image":
            slide_count = int(data.get("slide_count", 7))
            image_urls = [
                _issue_media_token(client, f"content/carousel/{job_id}/{n}.jpg")
                for n in range(slide_count)
            ]
            media_id = upload_carousel(ig_user_id, access_token, image_urls, caption)
        else:
            raise InstagramUploadError(f"지원하지 않는 플랫폼: {platform}")
        client.patch(f"/api/content/jobs/{job_id}/instagram-result", json={"status": "done", "media_id": media_id})
        append_log(LOGS_DIR, {"worker": "content", "status": "ig_uploaded", "job": job_id, "media": media_id})
    except Exception as e:  # noqa: BLE001
        try:
            client.patch(f"/api/content/jobs/{job_id}/instagram-result", json={"status": "failed", "error": str(e)[:500]})
        except Exception:  # noqa: BLE001
            pass
        append_log(LOGS_DIR, {"worker": "content", "status": "ig_upload_failed", "job": job_id, "error": str(e)[:300]})
    return True


def run_custom_brief_once(client) -> bool:
    """온디맨드 커스텀 주제 브리핑 생성. 대기 항목 없으면 False 반환."""
    import subprocess

    data = client.get("/api/brief/custom-topics/pending")
    topics = data.get("topics", []) if data else []
    if not topics:
        return False

    topic = topics[0]
    topic_id = topic["id"]
    name = topic["name"]

    # 온디맨드("지금 생성")는 항상 강제 재생성한다. --force가 멱등성 가드를 건너뛰고
    # 오늘치 기존 발행물을 교체한다(중복은 막되 의도적 재생성은 허용).
    append_log(LOGS_DIR, {"worker": "brief", "status": "start", "topic_id": topic_id, "name": name})

    brief_dir = Path(__file__).resolve().parent.parent.parent / "brief"
    generic_script = brief_dir / "generic_brief.py"
    venv_py = brief_dir / ".venv" / "bin" / "python"

    result = subprocess.run(
        [str(venv_py), str(generic_script), "--topic-id", topic_id, "--name", name, "--force"],
        capture_output=True, text=True,
    )

    if result.returncode == 0:
        append_log(LOGS_DIR, {"worker": "brief", "status": "done", "topic_id": topic_id})
        client.post(f"/api/brief/custom-topics/{topic_id}/result", json={})
    else:
        append_log(LOGS_DIR, {"worker": "brief", "status": "error", "topic_id": topic_id,
                               "stderr": result.stderr[-500:]})

    return True


def main() -> None:
    client = _build_client()
    append_log(LOGS_DIR, {"worker": "content", "status": "start"})
    while True:
        try:
            processed = run_once(client)
            if not processed:
                processed = run_upload_once(client)
            if not processed:
                processed = run_instagram_upload_once(client)
            if not processed:
                processed = run_custom_brief_once(client)
        except PortalError as e:
            append_log(LOGS_DIR, {"worker": "content", "status": "portal_error", "error": str(e)[:300]})
            processed = False
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
