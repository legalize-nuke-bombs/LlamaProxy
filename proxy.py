import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from llama_server import LlamaServerError

CHAT_PATHS = {"/v1/chat/completions", "/chat/completions"}
HOP_BY_HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "content-length", "host"}
CHUNK_SIZE = 64 * 1024


def create_proxy_server(port, server, cache):
    slot_lock = threading.Lock()

    class ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.forward_plain()

        def do_POST(self):
            if self.path.split("?")[0] in CHAT_PATHS:
                self.forward_chat()
            else:
                self.forward_plain()

        def do_OPTIONS(self):
            self.forward_plain()

        def read_body(self):
            length = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(length) if length else None

        def forward_plain(self):
            self.relay(self.read_body())

        def forward_chat(self):
            body = self.read_body()
            try:
                prompt = server.render_prompt(json.loads(body))
            except (ValueError, LlamaServerError):
                self.relay(body)
                return

            with slot_lock:
                entry = cache.prepare(prompt)
                status, reply = self.relay(body)
                if status == 200:
                    cache.complete(entry, prompt)
                    print_timings(reply)
                else:
                    cache.fail(entry)

        def relay(self, body):
            headers = {name: value for name, value in self.headers.items() if name.lower() not in HOP_BY_HOP_HEADERS}
            response = server.request(self.command, self.path, body, headers)

            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() not in HOP_BY_HOP_HEADERS:
                    self.send_header(name, value)

            content_length = response.getheader("Content-Length")
            if content_length is not None:
                reply = response.read()
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)
                return response.status, reply

            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            while chunk := response.read1(CHUNK_SIZE):
                self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            return response.status, None

        def log_message(self, format, *args):
            pass

    return ExclusiveThreadingHTTPServer(("0.0.0.0", port), ProxyHandler)


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"


def print_timings(reply):
    if reply is None:
        return
    try:
        timings = json.loads(reply).get("timings", {})
    except ValueError:
        return
    print(f"computed {timings.get('prompt_n')} tokens, took {timings.get('cache_n')} from cache, prompt {timings.get('prompt_ms', 0) / 1000:.1f} s, generated {timings.get('predicted_n')} tokens in {timings.get('predicted_ms', 0) / 1000:.1f} s")
