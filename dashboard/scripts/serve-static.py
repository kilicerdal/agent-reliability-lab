"""Serve the public export on loopback during browser verification."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class StaticServer(ThreadingHTTPServer):
    # Browser tabs request several independent chunks during hydration.
    request_queue_size = 64


def handler(*args, **kwargs):
    return SimpleHTTPRequestHandler(*args, directory="out", **kwargs)


with StaticServer(("127.0.0.1", 3314), handler) as server:
    server.serve_forever()
