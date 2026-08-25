# 로컬 이미지 생성 HTTP 서버 — POST /generate, GET /health. localhost 전용.
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from popory_imagegen import model
from popory_imagegen.model import ModelManager, build_pipe


def make_server(manager, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 액세스 로그 침묵
            pass

        def _json(self, code: int, obj: dict) -> None:
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/health":
                # guidance·negative_active 를 같이 노출한다 — CFG 가 꺼져 있으면 기형 방지
                # 네거티브가 조용히 무효라, 밖에서 보이지 않으면 아무도 모른다.
                self._json(200, {"loaded": getattr(manager, "loaded", False),
                                 "model": os.environ.get("POPORY_IMAGEGEN_MODEL", "realvisxl"),
                                 "guidance": model.GUIDANCE,
                                 "negative_active": model.negative_active(model.GUIDANCE)})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/generate":
                self._json(404, {"error": "not found"})
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:  # noqa: BLE001
                self._json(400, {"error": "bad json"})
                return
            prompt = body.get("prompt")
            if not isinstance(prompt, str) or not (1 <= len(prompt) <= 2000):
                self._json(400, {"error": "bad prompt"})
                return
            try:
                png = manager.generate(
                    prompt,
                    negative_prompt=body.get("negative_prompt"),
                    steps=body.get("steps"),
                    width=body.get("width"),
                    height=body.get("height"),
                )
            except ValueError:
                self._json(400, {"error": "bad prompt"})
                return
            except Exception as e:  # noqa: BLE001 — 생성 실패는 500
                self._json(500, {"error": str(e)[:200]})
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.end_headers()
            self.wfile.write(png)

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    port = int(os.environ.get("POPORY_IMAGEGEN_PORT", "8765"))
    idle = int(os.environ.get("POPORY_IMAGEGEN_IDLE_SECONDS", "600"))
    manager = ModelManager(loader=build_pipe, idle_seconds=idle)

    def unload_loop() -> None:
        while True:
            time.sleep(30)
            manager.maybe_unload()

    threading.Thread(target=unload_loop, daemon=True).start()
    httpd = make_server(manager, port=port)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
