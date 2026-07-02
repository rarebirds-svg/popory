# 포털 큐에서 컨텐츠 작업을 claim → claude 생성 → 결과 회신. __main__ 은 무한 poll 루프.
import datetime
import json
import os
import sys
import threading
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from popory_content.generate import generate, GenerateError, generate_youtube_post
from popory_content.video_prompt import build_shorts_system_prompt, build_shorts_user_message
from popory_content.video import make_video, VideoError, render_thumbnail, TMP
from popory_content.subtitles import to_srt
from popory_content.translate import translate_lines
from popory_content.youtube_upload import upload, upload_caption, set_thumbnail, post_comment
from popory_content.bookstore_links import build_purchase_comment_validated
from popory_content.options import parse_options, parse_shorts_options, SCENE_COUNT, SHORT_SCENE_COUNT, VOICE, STYLE
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log
from popory_content.instagram_image_prompt import build_carousel_system_prompt, build_carousel_user_message
from popory_content.instagram_image_contract import parse_carousel
from popory_content.instagram_image_render import render_carousel
from popory_content.instagram_upload import upload_reels, upload_carousel, InstagramUploadError
from popory_content.facebook_upload import upload_reels as fb_upload_reels

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
WORKER_AREA = "content-worker"
SUB_LANGS = ("ko", "en", "zh", "ja")


def _generate_carousel(*, topic: str, sources: list, style_samples: list, job_id: str, slide_count: int):
    """Claude CLI로 캐러셀 슬라이드 배열 생성."""
    from popory_content.generate import run_claude_cli
    sp = build_carousel_system_prompt(style_samples, slide_count=slide_count)
    um = build_carousel_user_message(topic, sources)
    return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_carousel, job_id=job_id)
POLL_INTERVAL_SECONDS = 20
# 서비스 JWT 수명. 60초는 시계 오차·느린 요청에 취약(일시 401 관측) → 여유 상향.
TOKEN_TTL_SECONDS = 300


def _is_claude_auth_failure(err: str) -> bool:
    """claude CLI 인증 만료 신호('Not logged in'). 상주 데몬 키체인 갱신 실패 시 발생."""
    return "Not logged in" in err or "Please run /login" in err


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
            mp4, scenes, meta, img_missing, img_total, cues = make_video(
                topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
                image_fetcher=lambda p: _safe_image(client, p, job_id),
                scene_count=SCENE_COUNT[opts["length"]],
                image_style_kw=STYLE[opts["image_style"]],
                voice=VOICE[opts["voice"]],
            )
            client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
            _store_subtitles(client, job_id, cues)
            script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
            _maybe_put_thumbnail(client, job_id, meta, portrait=False)
            _finalize_video(client, job_id, script, meta, img_missing, img_total)
        elif platform == "shorts":
            opts = parse_shorts_options(job.get("params_json"))
            mp4, scenes, meta, img_missing, img_total, cues = make_video(
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
            _store_subtitles(client, job_id, cues)
            script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
            _maybe_put_thumbnail(client, job_id, meta, portrait=True)
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
        elif platform == "youtube-post":
            draft, meta = generate_youtube_post(topic=job["topic"], job_id=job_id)
            _report(client, job_id, {"status": "review", "draft": draft, "meta": meta}, "review")
        else:
            draft, meta = generate(topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id)
            _report(client, job_id, {"status": "review", "draft": draft, "meta": meta}, "review")
    except Exception as e:  # noqa: BLE001 — 생성 실패는 failed 로 회신
        msg = str(e)
        _report(client, job_id, {"status": "failed", "error": msg[:2000]}, "failed")
        if _is_claude_auth_failure(msg):
            # 상주 데몬이 오래 떠 있으면 claude OAuth 토큰 갱신(키체인 재기록)에 실패해
            # 'Not logged in' 이 난다. 프로세스를 종료하면 launchd KeepAlive 가 새
            # 프로세스로 재기동해 키체인 접근이 복구된다(자가 치유). 잡은 이미 failed
            # 회신했으므로 재시도하면 새 워커가 처리한다.
            append_log(LOGS_DIR, {"worker": "content", "status": "auth_failure_exit", "job": job_id})
            sys.exit(1)
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
# 포털 readiness 하트비트(생성 가능 여부 페이지용).
HEARTBEAT_PATH = "/api/content/worker-heartbeat"
HEARTBEAT_INTERVAL_SECONDS = int(os.environ.get("POPORY_HEARTBEAT_INTERVAL", "30"))
IMAGEGEN_HEALTH_URL = IMAGEGEN_URL.replace("/generate", "/health")


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


def _imagegen_ok() -> bool:
    """로컬 imagegen 서버 /health 응답 여부."""
    try:
        return requests.get(IMAGEGEN_HEALTH_URL, timeout=3).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _cf_reset_date() -> str | None:
    """CF 무료 한도가 오늘 소진됐다면 리셋되는 다음 UTC 날짜(YYYY-MM-DD), 아니면 None."""
    if not _cf_exhausted_today():
        return None
    tomorrow = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=1)
    return tomorrow.strftime("%Y-%m-%d")


def heartbeat_payload() -> dict:
    """포털에 보고할 워커 생성 readiness 상태."""
    return {
        "cf_image_exhausted": _cf_exhausted_today(),
        "cf_reset_date": _cf_reset_date(),
        "imagegen_ok": _imagegen_ok(),
    }


def report_heartbeat(client) -> None:
    """포털에 하트비트 보고. 실패는 non-fatal(생성 작업에 영향 없음)."""
    try:
        client.post(HEARTBEAT_PATH, json=heartbeat_payload())
    except Exception as e:  # noqa: BLE001
        append_log(LOGS_DIR, {"worker": "content", "status": "heartbeat_failed", "error": str(e)[:200]})


def heartbeat_loop(client, stop: threading.Event) -> None:
    """백그라운드 스레드 — 메인 루프가 긴 생성 잡(10분 영상 등)에 블로킹돼도
    하트비트를 끊김 없이 보낸다. 예전엔 루프 사이에서만 보내 생성 중엔 끊겨
    포털이 워커를 오프라인으로 오판했다. PortalClient 는 호출마다 새 연결·서명이라
    메인 스레드와 client 를 공유해도 안전하다."""
    while not stop.is_set():
        report_heartbeat(client)
        stop.wait(HEARTBEAT_INTERVAL_SECONDS)


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


def _maybe_put_thumbnail(client, job_id: str, meta: dict, portrait: bool) -> None:
    """메타에 썸네일 키가 있으면 렌더 후 PUT. 실패는 로그만(영상 흐름 유지)."""
    try:
        out = TMP / f"thumb_{job_id}.jpg"
        res = render_thumbnail(meta.get("thumbnail_copy"), meta.get("thumbnail_image_prompt"), out,
                               portrait=portrait, image_fetcher=lambda p: _safe_image(client, p, job_id))
        if res:
            client.put_binary(f"/api/content/jobs/{job_id}/thumbnail", data=res.read_bytes(), content_type="image/jpeg")
            res.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        append_log(LOGS_DIR, {"worker": "content", "status": "thumbnail_failed", "job": job_id, "error": str(e)[:200]})


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


def _store_subtitles(client, job_id: str, cues: list) -> None:
    """KO cue를 EN/ZH/JA로 번역해 4개 .srt를 R2에 저장. 실패는 경고만(영상 정상)."""
    if not cues:
        return
    ko_lines = [text for _, _, text in cues]
    by_lang: dict[str, list[str]] = {"ko": ko_lines}
    try:
        tr = translate_lines(ko_lines, job_id=job_id)
    except Exception as e:  # noqa: BLE001
        tr = None
        append_log(LOGS_DIR, {"worker": "content", "status": "subs_translate_failed", "job": job_id, "error": str(e)[:200]})
    if tr:
        by_lang.update(tr)
    for lang, lines in by_lang.items():
        srt = to_srt([(st, en, lines[i]) for i, (st, en, _) in enumerate(cues)])
        try:
            client.put_binary(f"/api/content/jobs/{job_id}/subtitle/{lang}",
                              data=srt.encode("utf-8"), content_type="text/plain; charset=utf-8")
        except Exception as e:  # noqa: BLE001
            append_log(LOGS_DIR, {"worker": "content", "status": "subs_store_failed", "job": job_id, "lang": lang, "error": str(e)[:200]})


def _upload_captions(client, access_token: str, job_id: str, video_id: str) -> None:
    """저장된 .srt를 유튜브 caption 트랙으로 업로드. lang별 실패는 경고만(영상 정상)."""
    for lang in SUB_LANGS:
        try:
            srt = client.get_bytes(f"/api/content/jobs/{job_id}/subtitle/{lang}")
        except Exception:  # noqa: BLE001 — 없으면 건너뜀
            continue
        if not srt:
            continue
        try:
            upload_caption(access_token, video_id, lang, f"popory {lang}", srt)
        except Exception as e:  # noqa: BLE001
            append_log(LOGS_DIR, {"worker": "content", "status": "caption_failed", "job": job_id, "lang": lang, "error": str(e)[:200]})


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
        _upload_captions(client, data["access_token"], job_id, video_id)
        try:
            thumb = client.get_bytes(f"/api/content/jobs/{job_id}/thumbnail")
        except PortalError:
            thumb = None  # 썸네일 없음(구 콘텐츠) — 정상 건너뜀.
        if thumb:
            try:
                set_thumbnail(data["access_token"], video_id, thumb)
            except Exception as e:  # noqa: BLE001 — 썸네일 실패는 업로드 done 유지.
                append_log(LOGS_DIR, {"worker": "content", "status": "thumbnail_set_failed", "job": job_id, "error": str(e)[:200]})
        if data.get("category_slug") in ("book-review", "책리뷰") and data.get("book_title"):
            try:
                text = build_purchase_comment_validated(data["book_title"], data.get("book_author"))
                if text:
                    post_comment(data["access_token"], video_id, text)
                else:
                    append_log(LOGS_DIR, {"worker": "content", "status": "comment_skipped_no_valid_links", "job": job_id})
            except Exception as e:  # noqa: BLE001 — 댓글 실패는 업로드 done 유지.
                append_log(LOGS_DIR, {"worker": "content", "status": "comment_failed", "job": job_id, "error": str(e)[:200]})
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


def run_facebook_upload_once(client) -> bool:
    """Facebook 릴스 업로드 요청 1건 처리. 처리했으면 True."""
    data = client.post("/api/content/facebook/claim-upload", json=None)
    if not data:
        return False
    job_id = data["job_id"]
    page_id = data["page_id"]
    access_token = data["access_token"]
    caption = data.get("caption", "")
    try:
        video_url = _issue_media_token(client, f"content/video/{job_id}.mp4")
        video_id = fb_upload_reels(page_id, access_token, video_url, caption)
        client.patch(f"/api/content/jobs/{job_id}/facebook-result", json={"status": "done", "video_id": video_id})
        append_log(LOGS_DIR, {"worker": "content", "status": "fb_uploaded", "job": job_id, "video": video_id})
    except Exception as e:  # noqa: BLE001
        try:
            client.patch(f"/api/content/jobs/{job_id}/facebook-result", json={"status": "failed", "error": str(e)[:500]})
        except Exception:  # noqa: BLE001
            pass
        append_log(LOGS_DIR, {"worker": "content", "status": "fb_upload_failed", "job": job_id, "error": str(e)[:300]})
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


def run_cycle(client) -> bool:
    """한 폴 사이클. 생성·유튜브·IG·페이스북 업로드를 매번 각각 1회 시도한다.
    예전엔 생성 큐가 빌 때만 업로드를 claim 해서, 생성 백로그가 있으면 업로드가
    영구히 굶주렸다(준비중 정체). 이제 사이클마다 업로드 claim 을 시도하므로
    생성 1건이 도는 동안만 대기하고 그 직후 업로드가 처리된다(무한 starvation 제거).
    저순위 커스텀 브리핑은 다른 큐가 모두 비었을 때만 시도한다. 하나라도 처리하면 True.
    """
    did_gen = run_once(client)
    did_upload = run_upload_once(client)
    did_ig = run_instagram_upload_once(client)
    did_fb = run_facebook_upload_once(client)
    did_brief = False
    if not (did_gen or did_upload or did_ig or did_fb):
        did_brief = run_custom_brief_once(client)
    return did_gen or did_upload or did_ig or did_fb or did_brief


def main() -> None:
    client = _build_client()
    append_log(LOGS_DIR, {"worker": "content", "status": "start"})
    # 하트비트는 별도 데몬 스레드가 보낸다 — 생성 잡이 메인 루프를 오래 잡고 있어도 online 유지.
    threading.Thread(target=heartbeat_loop, args=(client, threading.Event()), daemon=True).start()
    while True:
        try:
            processed = run_cycle(client)
        except PortalError as e:
            append_log(LOGS_DIR, {"worker": "content", "status": "portal_error", "error": str(e)[:300]})
            processed = False
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
