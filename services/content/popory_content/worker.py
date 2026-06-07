# 포털 큐에서 컨텐츠 작업을 claim → claude 생성 → 결과 회신. __main__ 은 무한 poll 루프.
import os
import sys
import time
from pathlib import Path

from popory_content.generate import generate, GenerateError
from popory_content.video_prompt import build_shorts_system_prompt, build_shorts_user_message
from popory_content.video import make_video, VideoError
from popory_content.youtube_upload import upload
from popory_content.options import parse_options, parse_shorts_options, SCENE_COUNT, SHORT_SCENE_COUNT, VOICE, STYLE
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
WORKER_AREA = "content-worker"
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
            mp4, scenes, meta = make_video(
                topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
                image_fetcher=lambda p: _safe_image(client, p),
                scene_count=SCENE_COUNT[opts["length"]],
                image_style_kw=STYLE[opts["image_style"]],
                voice=VOICE[opts["voice"]],
            )
            client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
            script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
            _report(client, job_id, {"status": "review", "draft": script, "meta": meta}, "review")
        elif platform == "shorts":
            opts = parse_shorts_options(job.get("params_json"))
            mp4, scenes, meta = make_video(
                topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
                image_fetcher=lambda p: _safe_image(client, p),
                scene_count=SHORT_SCENE_COUNT[opts["length"]],
                image_style_kw=STYLE[opts["image_style"]],
                voice=VOICE[opts["voice"]],
                portrait=True,
                system_prompt_builder=build_shorts_system_prompt,
                user_msg_builder=build_shorts_user_message,
            )
            client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
            script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
            _report(client, job_id, {"status": "review", "draft": script, "meta": meta}, "review")
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


def _safe_image(client, prompt: str):
    """AI 이미지 1장. 실패하면 None(단색 폴백)."""
    try:
        return client.post_for_bytes("/api/content/ai-image", json={"prompt": prompt})
    except Exception:  # noqa: BLE001
        return None


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


def main() -> None:
    client = _build_client()
    append_log(LOGS_DIR, {"worker": "content", "status": "start"})
    while True:
        try:
            processed = run_once(client)
            if not processed:
                processed = run_upload_once(client)
        except PortalError as e:
            append_log(LOGS_DIR, {"worker": "content", "status": "portal_error", "error": str(e)[:300]})
            processed = False
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
