import os
import sys
import time

from llama_server import LlamaServer, LlamaServerError, find_running_llama_servers, kill_process
from proxy import create_proxy_server
from settings import ask_settings, load_settings, save_settings
from slot_cache import SlotCache

PROJECT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(PROJECT_DIRECTORY, "settings.json")
CACHE_DIRECTORY = os.path.join(PROJECT_DIRECTORY, "cache")
LOG_PATH = os.path.join(PROJECT_DIRECTORY, "llama-server.log")


def stop_running_llama_servers():
    pids = find_running_llama_servers()
    if not pids:
        return True
    answer = input(f"llama-server is already running (PID {', '.join(map(str, pids))}). Kill it? [y/N]: ")
    if answer.strip().lower() != "y":
        return False
    for pid in pids:
        kill_process(pid)
    return True


def main():
    settings = ask_settings(load_settings(SETTINGS_PATH))
    save_settings(settings, SETTINGS_PATH)

    os.makedirs(CACHE_DIRECTORY, exist_ok=True)
    server = LlamaServer(settings.llama_server_arguments(), CACHE_DIRECTORY, LOG_PATH)
    cache = SlotCache(server, CACHE_DIRECTORY, int(settings.cache_limit_gb * 2**30))
    try:
        proxy = create_proxy_server(settings.port, server, cache)
    except OSError as error:
        print(f"Can't listen on port {settings.port}: {error}")
        return

    if not stop_running_llama_servers():
        proxy.server_close()
        return

    try:
        started = time.perf_counter()
        server.start(on_waiting=lambda elapsed: print(f"\rLoading the model... {elapsed:.0f} s", end="", flush=True))
        print(f"\rModel loaded in {time.perf_counter() - started:.0f} s, llama-server log: {LOG_PATH}")
        print(f"Listening on port {settings.port}, Ctrl+C to stop")
        proxy.serve_forever()
    except LlamaServerError as error:
        print(f"\n{error}")
    except KeyboardInterrupt:
        try:
            cache.save_current()
        except LlamaServerError as error:
            print(f"Couldn't save the slot: {error}")
    finally:
        proxy.server_close()
        server.stop()


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
