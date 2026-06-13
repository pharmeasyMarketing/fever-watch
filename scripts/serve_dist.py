"""Threaded static server for previewing the built site (dist/fever-watch as web root).

`python -m http.server` is single-threaded and drops the browser's concurrent requests (notably the
~850KB data/grid.json), which makes the leaderboard look empty in preview. This serves the same files
with ThreadingHTTPServer so parallel asset + data fetches all complete, mirroring GitHub Pages.
"""
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist", "fever-watch")
PORT = 8138

if __name__ == "__main__":
    handler = partial(SimpleHTTPRequestHandler, directory=ROOT)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    print("serving %s at http://127.0.0.1:%d/" % (ROOT, PORT))
    httpd.serve_forever()
