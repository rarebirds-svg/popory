# 이미 만든 영상의 대본은 그대로 두고 음성·자막·영상만 다시 만드는 재렌더링 준비.
# 대본(포털 draft)은 사람이 고쳤을 수 있으므로 장면 문구의 기준이고, 이미지 프롬프트·카드는 meta.scenes
# (생성 때 남긴 장면 정보)에서 장면 순서대로 가져온다. 배경은 맥미니에 남은 이전 렌더 파일을 우선 다시 쓴다.
import re
from pathlib import Path
from typing import Any

from popory_content.video_prompt import ENDING_CTA_CAPTION, ENDING_CTA_IMAGE_PROMPT

# render_video 가 장면마다 남기는 배경 PNG(글자·스크림 없는 배경만). 이 표시를 image_prompt 로 넣으면
# 이미지 생성 대신 그 파일을 다시 쓴다 — render_video 는 프롬프트를 이미지 함수에 그대로 넘기기만 한다.
REUSE_PREFIX = "__reuse_bg__:"
# 배경도, 장면 정보도 남아 있지 않은 장면에 쓰는 프롬프트. 썸네일 배경 프롬프트가 있으면 그 톤을 따른다.
GENERIC_BG_PROMPT = ("quiet study with soft window light, stacked books and a wooden desk, no people, "
                     "no text, calm cinematic atmosphere")

_HEADER = re.compile(r"^\[(.+)\]\s*$")


class RerenderError(Exception):
    pass


def parse_script(draft: str | None) -> list[dict[str, str]]:
    """worker 가 저장한 대본("[제목]\\n내레이션" 블록을 빈 줄로 이은 것)을 장면 목록으로 되돌린다."""
    scenes: list[dict[str, str]] = []
    lines: list[str] = []
    for raw in (draft or "").splitlines():
        m = _HEADER.match(raw.strip())
        if m:
            if scenes:
                scenes[-1]["narration"] = "\n".join(lines).strip()
            scenes.append({"caption": m.group(1).strip(), "narration": ""})
            lines = []
        elif scenes:
            lines.append(raw)
    if scenes:
        scenes[-1]["narration"] = "\n".join(lines).strip()
    scenes = [s for s in scenes if s["narration"]]
    if not scenes:
        raise RerenderError("저장된 대본에서 장면을 찾지 못했습니다")
    return scenes


_BG_FILE = re.compile(r"^\d+\.png$")


def load_backgrounds(work: Path, count: int) -> dict[int, bytes]:
    """이전 렌더가 남긴 장면 배경(work/{i}.png)을 미리 읽어 둔다. 재렌더가 같은 이름으로 덮어쓰므로
    렌더를 시작하기 전에 모두 읽어야 한다.

    남은 배경 수가 대본 장면 수와 다르면 쓰지 않는다 — 사람이 장면을 더하거나 지웠으면 순서가 어긋나
    엉뚱한 배경이 붙는다."""
    found: dict[int, bytes] = {}
    try:
        names = [p.name for p in work.iterdir() if _BG_FILE.match(p.name)]
    except OSError:
        return found
    if len(names) != count:
        return found
    for i in range(count):
        p = work / f"{i}.png"
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if data:
            found[i] = data
    return found


def build_scenes(script: list[dict[str, str]], meta: dict[str, Any],
                 backgrounds: dict[int, bytes]) -> list[dict[str, Any]]:
    """대본 장면에 배경·카드를 붙인다. 배경은 남은 파일 → 저장된 이미지 프롬프트 → 대체 프롬프트 순.

    meta.scenes 는 장면 수가 대본과 같을 때만 믿는다 — 사람이 장면을 더하거나 지웠으면 순서가 어긋나
    엉뚱한 배경·카드가 붙는다."""
    saved = meta.get("scenes")
    saved = saved if isinstance(saved, list) and len(saved) == len(script) else None
    fallback_prompt = str(meta.get("thumbnail_image_prompt") or GENERIC_BG_PROMPT)
    out: list[dict[str, Any]] = []
    for i, s in enumerate(script):
        info = saved[i] if saved and isinstance(saved[i], dict) else {}
        scene: dict[str, Any] = {"caption": s["caption"], "narration": s["narration"]}
        if info.get("image_prompt"):
            scene["saved_prompt"] = str(info["image_prompt"])  # 배경을 다시 써도 다음 재렌더를 위해 남긴다
        if i in backgrounds:
            scene["image_prompt"] = f"{REUSE_PREFIX}{i}"
        elif info.get("image_prompt"):
            scene["image_prompt"] = str(info["image_prompt"])
        elif s["caption"] == ENDING_CTA_CAPTION:
            scene["image_prompt"] = ENDING_CTA_IMAGE_PROMPT
        else:
            scene["image_prompt"] = fallback_prompt
        if isinstance(info.get("card"), dict):
            scene["card"] = info["card"]
        out.append(scene)
    return out


def image_fetcher(backgrounds: dict[int, bytes], generate):
    """재사용 표시는 남은 배경으로, 그 밖의 프롬프트는 generate(prompt) 로 새로 만든다."""
    def fetch(prompt: str):
        if prompt.startswith(REUSE_PREFIX):
            return backgrounds.get(int(prompt[len(REUSE_PREFIX):]))
        return generate(prompt)
    return fetch


def scene_records(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """다음 재렌더를 위해 meta 에 남길 장면 정보(문구·이미지 프롬프트·카드)."""
    out = []
    for s in scenes:
        rec: dict[str, Any] = {"caption": s.get("caption", ""), "narration": s.get("narration", "")}
        prompt = s.get("image_prompt")
        if prompt and str(prompt).startswith(REUSE_PREFIX):
            prompt = s.get("saved_prompt")
        if prompt:
            rec["image_prompt"] = prompt
        if isinstance(s.get("card"), dict):
            rec["card"] = s["card"]
        out.append(rec)
    return out
