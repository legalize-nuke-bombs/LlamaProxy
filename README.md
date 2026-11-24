# About

A proxy for [llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-server` that keeps the prompt cache of many conversations on disk.

`llama-server` with one slot remembers only the last conversation. When several agents take turns, each of them makes the server process its whole prompt again, which takes minutes on a long context if the model doesn't fit in VRAM. The proxy keeps one conversation in the slot and the rest on disk: before a request it restores the cache that shares the longest beginning with the new prompt, and only the new tail gets processed. Reading a few gigabytes from an NVMe SSD takes a couple of seconds.

## Usage

Requires Python 3.10 or newer and `llama-server` in `PATH` (download it from the [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases)). No packages to install.

```
python main.py
```

The proxy asks for the model, the context size, the port, the cache limit on disk and extra `llama-server` arguments, and remembers the answers for the next run. If `llama-server` is already running, it offers to kill it. Then it starts its own `llama-server` and listens on all interfaces on the given port with the same API.

## How it works

* The request is rendered with the model's chat template (`/apply-template`) and compared with the prompts of the stored caches. The one with the longest common beginning wins, the one already in the slot wins a tie.
* The slot is saved to disk only when its content is about to be overwritten and isn't saved yet, and when the proxy stops, so the cache survives restarts.
* After each save, the least recently used caches are deleted while the total size is over the limit.
* `llama-server` runs with `-np 1`, `--cache-ram 0`, `--slot-save-path` and `--reasoning-preserve`. Its log is written to `llama-server.log`.
