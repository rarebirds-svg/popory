# 포털 큐에서 컨텐츠 작업을 claim → claude 생성 → 결과 회신. __main__ 은 무한 poll 루프.
import base64
import datetime
import json
import os
import subprocess
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
from popory_content.youtube_upload import upload, upload_caption, set_thumbnail
from popory_content.options import parse_options, parse_shorts_options, SCENE_COUNT, SHORT_SCENE_COUNT, VOICE, STYLE
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log
from popory_content.usage import cached_claude_usage
from popory_content.instagram_image_prompt import build_carousel_system_prompt, build_carousel_user_message
from popory_content.instagram_image_contract import parse_carousel
from popory_content.instagram_image_render import render_carousel
from popory_content.instagram_upload import upload_reels, upload_carousel, InstagramUploadError
from popory_content.facebook_upload import upload_reels as fb_upload_reels
from popory_content.youtube_playlist import assign_to_playlist
from popory_content.image_review import review_image, harden_prompt

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
WORKER_AREA = "content-worker"
SUB_LANGS = ("ko", "en", "zh", "ja")
# 업로드한 영상을 주제별 재생목록에 자동 분류(끄려면 0). 실패해도 업로드 done 은 유지.
PLAYLIST_ENABLED = os.environ.get("POPORY_YOUTUBE_PLAYLISTS", "1") != "0"


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
    """claude CLI 인증 만료 신호. 상주 데몬 키체인 갱신 실패 시 발생하며 문구가 여러 가지다."""
    return (
        "Not logged in" in err
        or "Please run /login" in err
        or "OAuth session expired" in err
        or "Failed to authenticate" in err
    )


NOTIFY_SH = "/Users/daegong/projects/popory/services/healthcheck/notify.sh"


def _notify_auth_failure() -> None:
    """인증 만료를 즉시 텔레그램으로 알린다. 사람이 /login 해야만 풀리기 때문이다.
    KeepAlive 재기동 루프에서 알림이 폭주하지 않게 발송측이 하루 1회로 억제한다."""
    try:
        subprocess.run(
            ["bash", NOTIFY_SH, "--once-key=worker_auth",
             "[popory] 콘텐츠 워커 중단 — Claude 인증 만료. 터미널에서 claude /login 후 잡을 재시도하세요."],
            capture_output=True, timeout=20,
        )
    except Exception:  # noqa: BLE001 — 알림 실패가 종료 경로를 막으면 안 된다.
        pass


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
            anchor = StyleAnchor(IMAGE_STYLE_ANCHOR)  # 작업마다 새로 — 톤이 작업 밖으로 새지 않게
            mp4, scenes, meta, img_missing, img_total, cues = make_video(
                topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
                image_fetcher=lambda p: _safe_image(client, p, job_id, anchor),
                scene_count=SCENE_COUNT[opts["length"]],
                image_style_kw=STYLE[opts["image_style"]],
                voice=VOICE[opts["voice"]],
            )
            client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
            _store_subtitles(client, job_id, cues)
            script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
            _maybe_put_thumbnail(client, job_id, meta, portrait=False, anchor=anchor)
            _finalize_video(client, job_id, script, meta, img_missing, img_total)
        elif platform == "shorts":
            opts = parse_shorts_options(job.get("params_json"))
            anchor = StyleAnchor(IMAGE_STYLE_ANCHOR)
            mp4, scenes, meta, img_missing, img_total, cues = make_video(
                topic=job["topic"], sources=sources, style_samples=samples, job_id=job_id,
                image_fetcher=lambda p: _safe_image(client, p, job_id, anchor),
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
            _maybe_put_thumbnail(client, job_id, meta, portrait=True, anchor=anchor)
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
            anchor = StyleAnchor(IMAGE_STYLE_ANCHOR)
            images = render_carousel(
                slides, image_fetcher=lambda p: _safe_image(client, p, job_id, anchor)
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
            _notify_auth_failure()
            sys.exit(1)
    return True


def _report(client, job_id: str, body: dict, status_label: str) -> None:
    """결과 회신. 회신 자체가 실패해도 poll 루프를 죽이지 않는다(작업은 running 으로 남음).
    실패 회신의 error 는 append_log 에도 실어 로컬 로그·job_logs 에 남긴다 —
    content_jobs.error 는 retry 가 NULL 로 지우므로 원문 유실을 막으려 이중화한다."""
    try:
        client.patch(f"/api/content/jobs/{job_id}/result", json=body)
        record = {"worker": "content", "status": status_label, "job": job_id}
        if body.get("error"):
            record["error"] = body["error"]
        append_log(LOGS_DIR, record)
    except Exception as e:  # noqa: BLE001 — 회신 실패는 로그만 남긴다
        append_log(LOGS_DIR, {"worker": "content", "status": "report_failed", "job": job_id, "error": str(e)[:300]})


IMAGE_MAX_ATTEMPTS = 3
IMAGE_BACKOFF = [2, 5]
# 검수 탈락 시 프롬프트를 강화해 다시 뽑는 최대 라운드. 0 이면 검수만 하고 재생성은 안 한다.
# 장면당 최악 1+N 회 생성이라 배치 시간에 직결된다.
IMAGE_REVIEW_ROUNDS = int(os.environ.get("POPORY_IMAGE_REVIEW_ROUNDS", "2"))
IMAGE_FAIL_RATIO = 0.5
IMAGEGEN_URL = os.environ.get("POPORY_IMAGEGEN_URL", "http://localhost:8765/generate")
# 로컬 fp32 SDXL/SD 생성은 맥미니 16GB 메모리 압박에서 장면당 ~110초가 걸린다.
# 120초는 빠듯해 종종 read timeout → 재시도 낭비 → 단색 폴백을 유발했다. 여유 상향.
IMAGE_TIMEOUT_SECONDS = int(os.environ.get("POPORY_IMAGEGEN_TIMEOUT", "300"))
# 1순위 = Cloudflare(무료 ~10k neurons/일). klein-4b → schnell → 로컬 RealVisXL 순으로 물러선다.
# 한도 소진(4006)은 두 모델이 같은 뉴런 풀을 쓰므로 모델을 바꿔도 안 풀린다 — CF 경로 전체를 접는다.
USE_CF_IMAGE = os.environ.get("POPORY_USE_CF_IMAGE", "1") != "0"
CF_AI_IMAGE_PATH = "/api/content/ai-image"
# 2026-08-22 실호출로 규약 검증 후 klein-4b 로 전환했다. schnell 보다 한 세대 뒤 모델이라
# 손·얼굴 기형이 덜하다. 되돌리려면 POPORY_CF_IMAGE_MODEL=schnell 하나면 된다(배포 불필요).
CF_IMAGE_MODEL = os.environ.get("POPORY_CF_IMAGE_MODEL", "klein-4b")
# klein 이 실패했을 때 물러설 모델. 같은 무료 한도라 로컬(장당 ~18초)보다 먼저 시도할 값어치가 있다.
# 빈 값이면 물러서지 않고 바로 로컬로 간다.
CF_IMAGE_FALLBACK_MODEL = os.environ.get("POPORY_CF_IMAGE_FALLBACK_MODEL", "schnell")
# klein 만 치수를 받는다(schnell 은 1024×1024 고정). 미설정이면 모델 기본값 — 정사각 원본의
# 세로 여유를 video.py 배경 패닝이 쓰고 있어서, 종횡비 변경은 별도 판단거리다.
CF_IMAGE_WIDTH = int(os.environ.get("POPORY_CF_IMAGE_WIDTH", "0")) or None
CF_IMAGE_HEIGHT = int(os.environ.get("POPORY_CF_IMAGE_HEIGHT", "0")) or None
# 스타일 앵커 — 한 작업의 첫 이미지를 줄여 두고 이후 장면에 참조로 물려 색감·조명을 잇는다.
# "전 장면 색감·조명 일관" 규칙을 프롬프트 문구가 아니라 모델 입력으로 강제하는 수단이다.
# klein 만 참조를 받으므로 schnell·로컬 폴백 경로에서는 자연히 비활성이다.
IMAGE_STYLE_ANCHOR = os.environ.get("POPORY_IMAGE_STYLE_ANCHOR", "1") != "0"
ANCHOR_MAX_PX = 480            # 라우트가 요구하는 512×512 미만
ANCHOR_MAX_BYTES = 400 * 1024  # 라우트 상한 512KB 안쪽
# 참조를 넣는 것만으로는 부족하다 — 실측에서 참조가 제대로 먹은 호출은 프롬프트가 image 0 을
# 명시했다. 명시 없이 이미지만 물리면 모델이 참조를 재현하려 들 수 있다.
ANCHOR_PROMPT_PREFIX = "Match the color grading, lighting and overall mood of image 0. "
CF_PROMPT_MAX = 1500  # 라우트 상한. 접두사를 붙여 넘기면 400 이라 그럴 땐 앵커를 포기한다.
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
        "usage": cached_claude_usage(),
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


def _anchor_b64(img: bytes) -> str | None:
    """참조 이미지로 쓸 수 있게 줄여 base64 로 만든다. 실패하면 None — 앵커는 있으면 좋은
    것이지 생성을 막을 이유가 아니다."""
    try:
        im = Image.open(BytesIO(img)).convert("RGB")
        im.thumbnail((ANCHOR_MAX_PX, ANCHOR_MAX_PX))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=85)
        raw = buf.getvalue()
        if not raw or len(raw) > ANCHOR_MAX_BYTES:
            return None
        return base64.b64encode(raw).decode()
    except Exception:  # noqa: BLE001
        return None


class StyleAnchor:
    """한 작업 안에서만 사는 스타일 앵커. 첫 이미지를 잡아 두고 이후 장면에 물린다.

    작업마다 새로 만든다 — 어제 영상의 톤이 오늘 영상에 새면 안 된다."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.b64: str | None = None

    def reference_images(self) -> list[str] | None:
        return [self.b64] if (self.enabled and self.b64) else None

    def adopt(self, img: bytes) -> None:
        """첫 이미지만 앵커로 잡는다. 이후 장면이 앵커를 덮어쓰면 톤이 서서히 흘러간다."""
        if self.enabled and self.b64 is None:
            self.b64 = _anchor_b64(img)


def _cf_payload(prompt: str, model: str, anchor: "StyleAnchor | None" = None) -> dict:
    """모델별 요청 본문. 라우트는 지원하지 않는 인자를 400 으로 돌려주므로 섞어 보내지 않는다."""
    body: dict = {"prompt": prompt, "model": model}
    if model != "schnell":
        if CF_IMAGE_WIDTH:
            body["width"] = CF_IMAGE_WIDTH
        if CF_IMAGE_HEIGHT:
            body["height"] = CF_IMAGE_HEIGHT
        refs = anchor.reference_images() if anchor else None
        if refs and len(prompt) + len(ANCHOR_PROMPT_PREFIX) <= CF_PROMPT_MAX:
            body["reference_images"] = refs
            body["prompt"] = ANCHOR_PROMPT_PREFIX + prompt
    return body


def _cf_models() -> list[str]:
    """시도할 CF 모델 순서. 폴백이 없거나 1순위와 같으면 한 번만 시도한다."""
    models = [CF_IMAGE_MODEL]
    if CF_IMAGE_FALLBACK_MODEL and CF_IMAGE_FALLBACK_MODEL != CF_IMAGE_MODEL:
        models.append(CF_IMAGE_FALLBACK_MODEL)
    return models


def _try_cloudflare(client, prompt: str, job_id: str = "?", anchor: "StyleAnchor | None" = None) -> bytes | None:
    """CF로 1장. 1순위 모델이 실패하면 폴백 모델까지 시도하고, 그래도 안 되면 None(→로컬 폴백).
    한도(4006/neurons)면 모델을 바꿔도 안 풀리므로 그날 소진 표시 후 즉시 물러난다."""
    for model in _cf_models():
        try:
            content = client.post_for_bytes(CF_AI_IMAGE_PATH, json=_cf_payload(prompt, model, anchor))
            _verify_image(content)
            return content
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "4006" in msg or "neuron" in msg.lower():
                _mark_cf_exhausted()
                return None
            # 모델별로 남긴다 — klein 만 계속 실패하면 전환을 되돌릴 근거가 여기 쌓인다.
            append_log(LOGS_DIR, {"worker": "content", "status": "cf_image_failed",
                                  "job": job_id, "model": model, "error": msg[:200]})
    return None


def _generate_image(client, prompt: str, job_id: str = "?", anchor: "StyleAnchor | None" = None):
    """배경 1장 생성(검수 없음). 1순위 CF flux-schnell(무료), 한도 소진·실패 시 로컬 폴백.
    깨진 응답은 검증으로 걸러 재시도, 최종 실패만 image_failed 로그+None."""
    if USE_CF_IMAGE and client is not None and not _cf_exhausted_today():
        img = _try_cloudflare(client, prompt, job_id, anchor)
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


def _safe_image(client, prompt: str, job_id: str = "?", anchor: "StyleAnchor | None" = None):
    """배경 1장 생성 + 이상 검수. 얼굴·인체 기형이나 눈 이상이 보이면 프롬프트에서 인물
    위험을 단계적으로 낮춰(뒷모습·실루엣 → 인물 제거) 재생성한다.

    끝까지 통과하지 못하면 **마지막 이미지를 그대로 쓴다** — 배경이 단색으로 비면
    _finalize_video 가 failed/review 로 떨어뜨려 영상 전체를 버리게 되는데, 기형이
    의심되는 한 장이 그보다 낫다. 재생성 라운드는 IMAGE_REVIEW_ROUNDS 로 제한해
    24장을 도는 배치가 늘어지지 않게 한다."""
    last_img = None
    for round_index in range(IMAGE_REVIEW_ROUNDS + 1):
        p = prompt if round_index == 0 else harden_prompt(prompt, round_index - 1)
        img = _generate_image(client, p, job_id, anchor)
        if img is None:
            break  # 생성 자체가 실패 — 프롬프트를 바꿔도 같으므로 중단(이미 로그됨)
        ok, reason = review_image(img, job_id)
        if ok:
            # 검수를 통과한 장면만 앵커가 된다. 기형 의심 이미지를 톤 기준으로 삼지 않는다.
            if anchor is not None:
                anchor.adopt(img)
            return img
        last_img = img
        append_log(LOGS_DIR, {"worker": "content", "status": "image_rejected", "job": job_id,
                              "round": round_index, "reason": reason, "prompt": p[:200]})
    if last_img is not None:
        append_log(LOGS_DIR, {"worker": "content", "status": "image_review_exhausted",
                              "job": job_id, "rounds": IMAGE_REVIEW_ROUNDS})
    return last_img


def _maybe_put_thumbnail(client, job_id: str, meta: dict, portrait: bool,
                         anchor: "StyleAnchor | None" = None) -> None:
    """메타에 썸네일 키가 있으면 렌더 후 PUT. 실패는 로그만(영상 흐름 유지).

    영상과 같은 앵커를 물린다 — 썸네일만 톤이 다르면 클릭해서 들어온 화면이 딴 영상 같다."""
    try:
        out = TMP / f"thumb_{job_id}.jpg"
        res = render_thumbnail(meta.get("thumbnail_copy"), meta.get("thumbnail_image_prompt"), out,
                               portrait=portrait,
                               image_fetcher=lambda p: _safe_image(client, p, job_id, anchor))
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
        # 구매 링크 고정 댓글은 여기서 달지 않는다 — 갓 업로드된 영상은 유튜브가 아직
        # 댓글을 받지 않아 403(insufficient permissions)이 100% 뜬다. 21시 backfill_comments
        # 가 준비된 뒤 같은 댓글을 단다(중복은 comment_exists 로 방지).
        if PLAYLIST_ENABLED:
            try:
                name = assign_to_playlist(data["access_token"], video_id,
                                          data.get("title", ""), data.get("tags", []))
                append_log(LOGS_DIR, {"worker": "content", "status": "playlist_added", "job": job_id, "playlist": name})
            except Exception as e:  # noqa: BLE001 — 재생목록 실패는 업로드 done 유지.
                append_log(LOGS_DIR, {"worker": "content", "status": "playlist_failed", "job": job_id, "error": str(e)[:200]})
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
