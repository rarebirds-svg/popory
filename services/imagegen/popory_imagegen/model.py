# SDXL 로컬 이미지 생성 — ModelManager(lazy-load·직렬화·유휴 언로드) + diffusers 실 로더.
import gc
import threading
import time
from typing import Any, Callable


class ModelManager:
    """파이프라인을 lazy-load 하고, 직렬화 생성하며, 유휴 시 언로드한다.
    loader()는 generate(prompt, **kw)->bytes 와 close() 를 가진 객체를 반환한다."""

    def __init__(self, loader: Callable[[], Any], idle_seconds: int = 600,
                 clock: Callable[[], float] = time.monotonic):
        self._loader = loader
        self._idle = idle_seconds
        self._clock = clock
        self._pipe: Any = None
        self._last_used: float | None = None
        self._lock = threading.Lock()

    def generate(self, prompt: str, **kw: Any) -> bytes:
        with self._lock:
            if self._pipe is None:
                self._pipe = self._loader()
            self._last_used = self._clock()
            return self._pipe.generate(prompt, **kw)

    def maybe_unload(self) -> None:
        with self._lock:
            if self._pipe is None or self._last_used is None:
                return
            if self._clock() - self._last_used >= self._idle:
                self._pipe.close()
                self._pipe = None
                self._last_used = None
                gc.collect()

    @property
    def loaded(self) -> bool:
        return self._pipe is not None
