import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field


def common_prefix_length(first, second):
    low, high = 0, min(len(first), len(second))
    while low < high:
        middle = (low + high + 1) // 2
        if first[:middle] == second[:middle]:
            low = middle
        else:
            high = middle - 1
    return low


@dataclass
class SlotEntry:
    model: str
    prompt: str = ""
    last_used: float = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def slot_file_name(self):
        return f"{self.id}.bin"

    @property
    def meta_file_name(self):
        return f"{self.id}.json"


class SlotCache:
    def __init__(self, server, directory, limit_bytes):
        self.server = server
        self.directory = directory
        self.limit_bytes = limit_bytes
        self.entries = self.load_entries()
        self.current = None
        self.current_saved = True

    def load_entries(self):
        entries = {}
        for name in os.listdir(self.directory):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(self.directory, name), encoding="utf-8") as file:
                entry = SlotEntry(**json.load(file))
            if os.path.isfile(self.path_of(entry.slot_file_name)):
                entries[entry.id] = entry
        return entries

    def path_of(self, file_name):
        return os.path.join(self.directory, file_name)

    def prepare(self, prompt):
        current_length = common_prefix_length(self.current.prompt, prompt) if self.current else 0
        stored, stored_length = self.find_closest_stored(prompt)

        if stored is not None and stored_length > current_length:
            self.save_current(keeping=stored)
            self.server.restore_slot(stored.slot_file_name)
            self.current = stored
            self.current_saved = True
            current_length = stored_length
            print(f"restored {stored.id[:8]} from disk")
        elif self.current is not None and current_length < len(self.current.prompt):
            self.save_current()

        if self.current is not None and current_length == len(self.current.prompt):
            return self.current
        return SlotEntry(model=self.server.model_path)

    def find_closest_stored(self, prompt):
        candidates = [
            (entry, common_prefix_length(entry.prompt, prompt))
            for entry in self.entries.values()
            if entry is not self.current and entry.model == self.server.model_path
        ]
        return max(candidates, key=lambda candidate: candidate[1], default=(None, 0))

    def complete(self, entry, prompt):
        entry.prompt = prompt
        entry.last_used = time.time()
        self.entries[entry.id] = entry
        self.current = entry
        self.current_saved = False

    def fail(self, entry):
        if entry is not self.current:
            self.current = None
            self.current_saved = True

    def save_current(self, keeping=None):
        if self.current is None or self.current_saved:
            return

        started = time.perf_counter()
        self.server.save_slot(self.current.slot_file_name)
        with open(self.path_of(self.current.meta_file_name), "w", encoding="utf-8") as file:
            json.dump(asdict(self.current), file, ensure_ascii=False)
        self.current_saved = True
        size_gb = os.path.getsize(self.path_of(self.current.slot_file_name)) / 2**30
        print(f"saved {self.current.id[:8]} to disk: {size_gb:.2f} GB in {time.perf_counter() - started:.1f} s")

        self.evict_oldest_over_limit(keeping)

    def evict_oldest_over_limit(self, keeping):
        while self.stored_bytes() > self.limit_bytes:
            evictable = [entry for entry in self.entries.values() if entry is not self.current and entry is not keeping]
            if not evictable:
                return
            oldest = min(evictable, key=lambda entry: entry.last_used)
            os.remove(self.path_of(oldest.slot_file_name))
            os.remove(self.path_of(oldest.meta_file_name))
            del self.entries[oldest.id]
            print(f"evicted {oldest.id[:8]}")

    def stored_bytes(self):
        return sum(
            os.path.getsize(self.path_of(entry.slot_file_name))
            for entry in self.entries.values()
            if os.path.isfile(self.path_of(entry.slot_file_name))
        )
