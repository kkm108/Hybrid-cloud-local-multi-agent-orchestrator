"""Local LLM backends (§6).

The ``LLMBackend`` interface is shared by the deterministic ``MockBackend``
(default) and the torch-based ``TransformersBackend`` (``gpu`` marker).
Sampling kwargs map 1:1 onto ``transformers`` ``generate()``.

Defaults (§6): temp .7, top_p .9, top_k 50, max_tokens 512, rep_penalty 1.0.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

DEFAULTS = {
    "model": "mock",
    "device": "cpu",
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 50,
    "max_tokens": 512,
    "repetition_penalty": 1.0,
}

# Map protocol config verbs (§5) to internal config keys.
VERB_TO_KEY = {
    "TEMPERATURE": "temperature",
    "TOP_P": "top_p",
    "TOP_K": "top_k",
    "MAX_TOKENS": "max_tokens",
    "REPETITION_PENALTY": "repetition_penalty",
    "SYSTEM_PROMPT": "system_prompt",
}


class LLMBackend(ABC):
    """Backend interface for a single local inference endpoint."""

    def __init__(self, config: dict | None = None) -> None:
        merged = dict(DEFAULTS)
        if config:
            merged.update({k: v for k, v in config.items() if v is not None})
        self._config = merged

    @property
    def config(self) -> dict:
        return dict(self._config)

    def update_config(self, key: str, value) -> None:
        """Apply a single config update in place."""
        if key not in DEFAULTS and key not in ("system_prompt",):
            raise KeyError(f"unknown config key: {key}")
        self._config[key] = value

    def apply(self, **kwargs) -> None:
        for key, value in kwargs.items():
            self.update_config(key, value)

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Return a completion for ``prompt``."""


class MockBackend(LLMBackend):
    """Deterministic, dependency-free backend (default)."""

    def generate(self, prompt: str) -> str:
        return f"mock-reply:{prompt}"


class TransformersBackend(LLMBackend):
    """torch/transformers backend with CPU fallback (``gpu`` marker).

    The heavy imports are performed lazily so importing the module never
    requires torch (keeps default CI green).
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._pipe = None

    def _ensure_loaded(self):
        if self._pipe is not None:
            return self._pipe
        try:
            import torch  # noqa: F401
            from transformers import pipeline  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - gpu path only
            raise RuntimeError("transformers/torch not installed (extra `gpu`)") from exc

        device = 0 if torch.cuda.is_available() else -1
        self._config["device"] = "cuda" if device == 0 else "cpu"
        self._pipe = pipeline("text-generation", model=self._config["model"], device=device)
        return self._pipe

    def generate(self, prompt: str) -> str:
        pipe = self._ensure_loaded()
        kwargs = {
            "max_new_tokens": int(self._config["max_tokens"]),
            "temperature": self._config["temperature"],
            "top_p": self._config["top_p"],
            "top_k": int(self._config["top_k"]),
            "repetition_penalty": self._config["repetition_penalty"],
            "do_sample": True,
        }
        out = pipe(prompt, **kwargs)
        return out[0]["generated_text"]
