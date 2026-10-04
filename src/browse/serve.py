"""Serve the evidence page on localhost. Nothing is written and no key is read."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.browse.page import render_page
from src.browse.snapshot import BrowserPaths, build_snapshot


def serve(paths: BrowserPaths | None = None, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Block while serving one rendered page."""
    page = render_page(build_snapshot(paths)).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] not in {"/", "/index.html"}:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Evidence browser: http://{host}:{port}", flush=True)
    print("Local only. No model call. Stop with Ctrl+C.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
