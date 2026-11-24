import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import time

EXECUTABLE_NAME = "llama-server"
HOST = "127.0.0.1"


def find_running_llama_servers():
    if os.name == "nt":
        output = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {EXECUTABLE_NAME}.exe"], capture_output=True, text=True, errors="replace").stdout
        return [int(line.split('","')[1]) for line in output.splitlines() if line.startswith(f'"{EXECUTABLE_NAME}')]
    output = subprocess.run(["pgrep", "-x", EXECUTABLE_NAME], capture_output=True, text=True).stdout
    return [int(pid) for pid in output.split()]


def kill_process(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    else:
        os.kill(pid, signal.SIGTERM)


def find_free_port():
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


class LlamaServerError(Exception):
    pass


class LlamaServer:
    def __init__(self, arguments, slot_directory, log_path):
        self.arguments = arguments
        self.slot_directory = slot_directory
        self.log_path = log_path
        self.port = find_free_port()
        self.process = None
        self.model_path = None

    def start(self, on_waiting):
        executable = shutil.which(EXECUTABLE_NAME)
        if executable is None:
            raise LlamaServerError(f"{EXECUTABLE_NAME} is not in PATH")

        command = [
            executable, *self.arguments,
            "--host", HOST, "--port", str(self.port),
            "-np", "1", "--cache-ram", "0",
            "--slot-save-path", self.slot_directory,
            "--reasoning-preserve",
        ]
        log = open(self.log_path, "w", encoding="utf-8")
        new_process_group = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, creationflags=new_process_group, start_new_session=os.name != "nt")

        self.wait_until_healthy(on_waiting)
        self.model_path = self.get_json("/props")["model_path"]

    def wait_until_healthy(self, on_waiting):
        started = time.perf_counter()
        while True:
            on_waiting(time.perf_counter() - started)
            if self.process.poll() is not None:
                raise LlamaServerError(f"{EXECUTABLE_NAME} exited with code {self.process.returncode}, see {self.log_path}")
            try:
                if self.request("GET", "/health").status == 200:
                    return
            except OSError:
                pass
            time.sleep(0.5)

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.process.wait()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(HOST, self.port)
        connection.request(method, path, body, headers or {})
        return connection.getresponse()

    def get_json(self, path):
        return self.read_json(self.request("GET", path))

    def post_json(self, path, payload):
        return self.read_json(self.request("POST", path, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"}))

    @staticmethod
    def read_json(response):
        body = response.read()
        if response.status != 200:
            raise LlamaServerError(f"HTTP {response.status}: {body.decode('utf-8', 'replace')}")
        return json.loads(body)

    def render_prompt(self, chat_request):
        return self.post_json("/apply-template", chat_request)["prompt"]

    def save_slot(self, file_name):
        self.post_json("/slots/0?action=save", {"filename": file_name})

    def restore_slot(self, file_name):
        self.post_json("/slots/0?action=restore", {"filename": file_name})
