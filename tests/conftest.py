"""Test-wide setup. Runs before test modules import agentic_tcg (and so before .env is loaded)."""

import os

# Tests must never send traces to LangSmith, even when .env enables tracing.
# Set before .env is loaded (load_dotenv does not override existing variables);
# the langsmith SDK caches these, so they cannot be switched off later with monkeypatch.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langsmith import utils as _ls_utils  # noqa: E402

_ls_utils.get_env_var.cache_clear()
