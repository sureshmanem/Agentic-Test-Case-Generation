"""CLI: generate test cases with the baseline and/or the agent.

    uv run python -m agentic_tcg.generate                      # all requirements, both modes
    uv run python -m agentic_tcg.generate --mode agent -r R4,R6
"""

import argparse
import sys

from agentic_tcg.config import get_settings
from agentic_tcg.models import load_requirement, load_requirements
from agentic_tcg.pipeline import MODES, run_agent, run_baseline, save_result
from agentic_tcg.retriever import KnowledgeBase
from agentic_tcg.traceability import build_traceability


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=[*MODES, "both"], default="both")
    parser.add_argument("-r", "--requirements", help="Comma-separated ids, e.g. R1,R4 (default: all)")
    args = parser.parse_args(argv)

    if not get_settings().has_api_key:
        print("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.", file=sys.stderr)
        return 2

    reqs = [load_requirement(r.strip()) for r in args.requirements.split(",")] if args.requirements else load_requirements()
    modes = MODES if args.mode == "both" else (args.mode,)
    kb = KnowledgeBase() if "agent" in modes else None

    for req in reqs:
        for mode in modes:
            result = run_baseline(req) if mode == "baseline" else run_agent(req, kb=kb)
            path = save_result(result)
            coverage = build_traceability(req, result.suite).coverage
            print(f"{req.id} {mode:8} {len(result.suite.test_cases):3} tests  coverage {coverage:4.0%}  "
                  f"{result.llm_calls} LLM call(s)  {result.elapsed_seconds:6.1f}s  -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
