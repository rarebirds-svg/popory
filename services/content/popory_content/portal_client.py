# portal API HTTP 호출 헬퍼. Bearer 자동 부착 + 응답 → CLI exit code 매핑.
import time
from typing import Any, Callable

import requests


class PortalError(Exception):
    """exit_code 속성을 갖는 호출 실패."""
    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code


class PortalClient:
    def __init__(
        self,
        *,
        base_url: str,
        token_provider: Callable[[], str],
        timeout: float = 10.0,
        retry_backoff_seconds: float = 2.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token_provider = token_provider
        self.timeout = timeout
        self.retry_backoff_seconds = retry_backoff_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token_provider()}",
            "Content-Type": "application/json",
        }

    def get(self, path: str) -> Any:
        return self._call("GET", path, body=None)

    def patch(self, path: str, *, json: Any) -> Any:
        return self._call("PATCH", path, body=json)

    def post(self, path: str, *, json: Any = None) -> Any:
        return self._call("POST", path, body=json)

    def put_binary(self, path: str, *, data: bytes, content_type: str) -> Any:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token_provider()}", "Content-Type": content_type}
        try:
            resp = requests.put(url, headers=headers, data=data, timeout=60)
        except requests.RequestException as e:
            raise PortalError(f"network: {e}", exit_code=5) from e
        if resp.status_code >= 400:
            raise PortalError(f"video upload {resp.status_code}: {resp.text[:200]}", exit_code=4)
        return resp.json() if resp.content else {}

    def post_for_bytes(self, path: str, *, json: Any) -> bytes:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token_provider()}", "Content-Type": "application/json"}
        try:
            resp = requests.post(url, headers=headers, json=json, timeout=60)
        except requests.RequestException as e:
            raise PortalError(f"network: {e}", exit_code=5) from e
        if resp.status_code >= 400:
            raise PortalError(f"ai-image {resp.status_code}: {resp.text[:200]}", exit_code=4)
        return resp.content

    def _call(self, method: str, path: str, *, body: Any) -> Any:
        url = f"{self.base_url}{path}"
        attempts = 2  # 원호출 + 5xx 재시도 1회
        last_status: int | None = None
        last_text = ""
        for i in range(attempts):
            try:
                resp = requests.request(method, url, headers=self._headers(),
                                        json=body, timeout=self.timeout)
            except requests.RequestException as e:
                if i + 1 < attempts:
                    time.sleep(self.retry_backoff_seconds)
                    continue
                raise PortalError(f"network: {e}", exit_code=5) from e
            last_status, last_text = resp.status_code, resp.text
            if resp.status_code < 400:
                return resp.json() if resp.content else {}
            if resp.status_code in (401, 403):
                raise PortalError(f"auth {resp.status_code}: {resp.text}", exit_code=3)
            if 400 <= resp.status_code < 500:
                raise PortalError(f"client {resp.status_code}: {resp.text}", exit_code=4)
            if i + 1 < attempts:
                time.sleep(self.retry_backoff_seconds)
                continue
        raise PortalError(f"server {last_status} after retry: {last_text}", exit_code=5)
