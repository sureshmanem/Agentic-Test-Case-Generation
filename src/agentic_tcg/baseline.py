"""Baseline: one prompt, requirement in, test cases out. The agent is compared against this."""

from agentic_tcg import prompts
from agentic_tcg.llm import LLMTestSuite, StructuredLLM, invoke_structured, to_test_suite
from agentic_tcg.models import Requirement, TestSuite


def generate_baseline(requirement: Requirement, llm: StructuredLLM) -> TestSuite:
    out = invoke_structured(
        llm,
        LLMTestSuite,
        prompts.BASELINE_SYSTEM,
        prompts.BASELINE_USER.format(requirement=requirement.to_prompt_text()),
    )
    return to_test_suite(requirement.id, out)
