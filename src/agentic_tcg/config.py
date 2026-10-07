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
load_dotenv(ROOT / ".env")

DEFAULT_LANGSMITH_PROJECT = "agentic-test-case-generation"
# Send traces to this project instead of LangSmith's "default" unless the user chose one
os.environ.setdefault("LANGSMITH_PROJECT", DEFAULT_LANGSMITH_PROJECT)

# Overridable so tests and demos can use scratch folders
OUTPUTS_DIR = Path(os.getenv("AGENTIC_TCG_OUTPUTS_DIR") or ROOT / "outputs")
REPORTS_DIR = Path(os.getenv("AGENTIC_TCG_REPORTS_DIR") or ROOT / "reports")


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


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def tracing_enabled() -> bool:
    """LangSmith tracing is on when LANGSMITH_TRACING is true and an API key is set
    (the legacy LANGCHAIN_* names are accepted too)."""
    flag = os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2")
    key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY") or ""
    return _truthy(flag) and bool(key) and not key.startswith("lsv2_...")


def langsmith_project() -> str:
    return os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or DEFAULT_LANGSMITH_PROJECT


def flush_traces() -> None:
    """Make sure queued LangSmith traces are sent before a CLI process exits."""
    if tracing_enabled():
        from langchain_core.tracers.langchain import wait_for_all_tracers

        wait_for_all_tracers()


def get_settings() -> Settings:
    return Settings()
