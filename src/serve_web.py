"""Local preview server for web/ (port 8765).

POST /save/<name>.jpg with a data: URL body writes a still into previews/; the
3D page's window.VAYU.shot() makes those stills.
"""
import base64
import http.server
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB, OUT = ROOT / "web", ROOT / "previews"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8"}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):   # same skeleton the artifact host adds
            page = (WEB / "index.html").read_text()
            body = ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" '
                    'content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>'
                    + page + "</body></html>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):
        m = re.fullmatch(r"/save/([\w-]+\.(?:jpg|png))", self.path)
        if not m:
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        dest = (WEB if m.group(1).startswith("vayu-poster") else OUT) / m.group(1)
        dest.write_bytes(base64.b64decode(body.split(",", 1)[1]))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


http.server.ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
