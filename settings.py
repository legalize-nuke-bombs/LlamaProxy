import json
import os
from dataclasses import asdict, dataclass, fields

KV_CACHE_TYPES = ("f16", "q8_0", "q4_0")


@dataclass
class Settings:
    model: str = ""
    context_k_tokens: int = 256
    port: int = 8090
    cache_limit_gb: int = 20
    kv_cache_type: str = "q8_0"

    def model_arguments(self):
        if os.path.isfile(self.model):
            return ["-m", self.model]
        return ["-hf", self.model]

    def llama_server_arguments(self):
        return [
            *self.model_arguments(),
            "-c", str(self.context_k_tokens * 1024),
            "-ctk", self.kv_cache_type, "-ctv", self.kv_cache_type,
        ]


def load_settings(path):
    if not os.path.isfile(path):
        return Settings()
    with open(path, encoding="utf-8") as file:
        saved = json.load(file)
    known = {field.name for field in fields(Settings)}
    settings = Settings(**{name: value for name, value in saved.items() if name in known})
    settings.cache_limit_gb = int(settings.cache_limit_gb)
    return settings


def save_settings(settings, path):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(asdict(settings), file, indent=2, ensure_ascii=False)


def ask_settings(previous):
    print("Enter keeps the value in brackets")
    return Settings(
        model=ask("Model, .gguf path or Hugging Face repo:quant", previous.model, str),
        context_k_tokens=ask("Context, K tokens", previous.context_k_tokens, int),
        port=ask("Port", previous.port, int),
        cache_limit_gb=ask("Disk cache limit, GB", previous.cache_limit_gb, int),
        kv_cache_type=ask(f"KV cache type, {' / '.join(KV_CACHE_TYPES)}", previous.kv_cache_type, parse_kv_cache_type),
    )


def parse_kv_cache_type(answer):
    if answer not in KV_CACHE_TYPES:
        raise ValueError
    return answer


def ask(label, previous, parse):
    prompt = f"{label} [{previous}]: " if previous != "" else f"{label}: "
    while True:
        answer = input(prompt).strip()
        if not answer:
            if previous != "":
                return previous
            continue
        try:
            return parse(answer)
        except ValueError:
            print(f"Can't use '{answer}'")
