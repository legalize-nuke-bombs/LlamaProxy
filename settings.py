import json
import os
import shlex
from dataclasses import asdict, dataclass

DEFAULT_EXTRA_ARGUMENTS = "-fa on -ctk q8_0 -ctv q8_0"


@dataclass
class Settings:
    model: str = ""
    context_k_tokens: int = 256
    port: int = 8090
    cache_limit_gb: float = 20
    extra_arguments: str = DEFAULT_EXTRA_ARGUMENTS

    def model_arguments(self):
        if os.path.isfile(self.model):
            return ["-m", self.model]
        return ["-hf", self.model]

    def llama_server_arguments(self):
        extra = [argument.strip('"') for argument in shlex.split(self.extra_arguments, posix=False)]
        return [*self.model_arguments(), "-c", str(self.context_k_tokens * 1024), *extra]


def load_settings(path):
    if not os.path.isfile(path):
        return Settings()
    with open(path, encoding="utf-8") as file:
        return Settings(**json.load(file))


def save_settings(settings, path):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(asdict(settings), file, indent=2, ensure_ascii=False)


def ask_settings(previous):
    return Settings(
        model=ask("Model (.gguf path or Hugging Face repo:quant)", previous.model, str, required=True),
        context_k_tokens=ask("Context, K tokens", previous.context_k_tokens, int),
        port=ask("Port", previous.port, int),
        cache_limit_gb=ask("Cache limit on disk, GB", previous.cache_limit_gb, float),
        extra_arguments=ask("Extra llama-server arguments, - for none", previous.extra_arguments, lambda answer: "" if answer == "-" else answer),
    )


def ask(label, previous, parse, required=False):
    while True:
        answer = input(f"{label} [{previous}]: ").strip()
        if not answer:
            if required and not previous:
                continue
            return previous
        try:
            return parse(answer)
        except ValueError:
            print(f"Can't read '{answer}'")
