import pytest
from openai.lib._pydantic import to_strict_json_schema

from agentic_tcg.baseline import generate_baseline
from agentic_tcg.llm import LLMTestCase, LLMTestSuite, LLMUntestable, parse_test_data
from agentic_tcg.models import load_requirement
from fakes import FakeLLM


def assert_openai_strict(schema: dict) -> None:
    """OpenAI strict mode: every object forbids extra keys and requires all of its properties."""
    if schema.get("type") == "object" or "properties" in schema:
        assert schema.get("additionalProperties") is False, schema
        assert set(schema.get("required", [])) == set(schema.get("properties", {})), schema
    for value in schema.values():
        if isinstance(value, dict):
            assert_openai_strict(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    assert_openai_strict(item)


def strict_schema(model) -> dict:
    """The schema the OpenAI SDK sends for a Pydantic response_format in strict mode."""
    return to_strict_json_schema(model)


def test_llm_test_suite_schema_is_openai_strict_compatible():
    assert_openai_strict(strict_schema(LLMTestSuite))


def test_parse_test_data_handles_bad_json():
    assert parse_test_data('{"agency": "FITCH"}') == {"agency": "FITCH"}
    assert parse_test_data("") == {}
    assert parse_test_data("not json") == {"raw": "not json"}
    assert parse_test_data("[1, 2]") == {"value": [1, 2]}


def fake_case(tc_id: str, covers: list[str]) -> LLMTestCase:
    return LLMTestCase(
        id=tc_id, title=f"Test {tc_id}", type="positive", priority="high", preconditions=[],
        steps=["do it"], test_data_json='{"symbol": "Baa3"}', expected_result="accepted", covers=covers,
    )


def test_baseline_single_call_and_conversion():
    def handler(schema, system, user):
        assert schema is LLMTestSuite
        return LLMTestSuite(
            test_cases=[fake_case("x", ["R1-AC1"]), fake_case("x", ["R1-AC2"])],
            clarification_questions=["Which error for WD under MOODYS?"],
            untestable_acs=[LLMUntestable(ac_id="R1-AC6", reason="demo")],
        )

    llm = FakeLLM(handler)
    suite = generate_baseline(load_requirement("R1"), llm)

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["kwargs"] == {"method": "json_schema", "strict": True}
    assert "R1-AC6" in call["user"] and "senior QA engineer" in call["system"]
    assert [tc.id for tc in suite.test_cases] == ["R1-TC01", "R1-TC02"]  # renumbered, unique
    assert suite.test_cases[0].test_data == {"symbol": "Baa3"}
    assert suite.clarification_questions == ["Which error for WD under MOODYS?"]
    assert suite.untestable_acs == {"R1-AC6": "demo"}


@pytest.mark.llm
def test_baseline_live_openai():
    from agentic_tcg.config import get_settings
    from agentic_tcg.llm import get_chat_model

    if not get_settings().has_api_key:
        pytest.skip("OPENAI_API_KEY not set")
    suite = generate_baseline(load_requirement("R3"), get_chat_model())
    assert suite.test_cases and all(tc.covers for tc in suite.test_cases)
