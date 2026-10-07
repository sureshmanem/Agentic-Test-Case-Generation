"""Settings loaded from environment variables (and .env at the project root)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
REQUIREMENTS_DIR = DATA_DIR / "requirements"
GOLDEN_DIR = DATA_DIR / "golden"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
OUTPUTS_DIR = ROOT / "outputs"
REPORTS_DIR = ROOT / "reports"
CHROMA_DIR = ROOT / ".chroma"

load_dotenv(ROOT / ".env")


def _env(name: str, default: str) -> str:
    return os.getenv(name) or default


@dataclass(frozen=True)
class Settings:
    generation_model: str = field(default_factory=lambda: _env("GENERATION_MODEL", "gpt-4.1"))
    judge_model: str = field(default_factory=lambda: _env("JUDGE_MODEL", "gpt-4.1-mini"))
    embedding_model: str = field(default_factory=lambda: _env("EMBEDDING_MODEL", "text-embedding-3-small"))
    max_self_check_iterations: int = field(default_factory=lambda: int(_env("MAX_SELF_CHECK_ITERATIONS", "2")))
    retrieval_k: int = field(default_factory=lambda: int(_env("RETRIEVAL_K", "4")))

    @property
    def has_api_key(self) -> bool:
        key = os.getenv("OPENAI_API_KEY", "")
        return bool(key) and not key.startswith("sk-...")


def get_settings() -> Settings:
    return Settings()
