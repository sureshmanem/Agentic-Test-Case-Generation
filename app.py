"""Streamlit demo: agentic test case generation vs. a single-prompt baseline.

    uv run streamlit run app.py
"""

import json

import pandas as pd
import streamlit as st

from agentic_tcg import config
from agentic_tcg.config import get_settings, langsmith_project, tracing_enabled
from agentic_tcg.evaluate import (
    build_report,
    default_judges,
    evaluate_requirement,
    load_records,
    send_feedback,
    update_reports,
)
from agentic_tcg.models import Requirement, TestSuite, load_golden, load_requirements
from agentic_tcg.pipeline import MODES, GenerationResult, load_result, run_agent, run_baseline, save_result
from agentic_tcg.renderers import questions_text, to_gherkin, to_pytest, to_rows, traceability_markdown
from agentic_tcg.traceability import build_traceability

st.set_page_config(page_title="Agentic Test Case Generation", page_icon="🧪", layout="wide")

MODE_LABEL = {"baseline": "Baseline (1 prompt)", "agent": "Agent (LangGraph)"}

AGENT_GRAPH = """
digraph {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#eef2ff", color="#6366f1", fontname="Helvetica", fontsize=11];
  edge [color="#64748b", fontname="Helvetica", fontsize=9];
  analyse -> retrieve -> plan -> generate -> review;
  review -> revise [label="findings", style=dashed];
  revise -> review;
  review -> finalize [label="clean / limit", style=dashed];
  retrieve [fillcolor="#ecfdf5", color="#10b981", label="retrieve\\n(Chroma)"];
}
"""


@st.cache_resource(show_spinner="Building knowledge base ...")
def knowledge_base():
    from agentic_tcg.retriever import KnowledgeBase

    return KnowledgeBase()


@st.cache_data
def requirements() -> dict[str, Requirement]:
    return {r.id: r for r in load_requirements()}


@st.cache_data(ttl=300, show_spinner=False)
def langsmith_url(run_id: str) -> str | None:
    """Link to a run in LangSmith (None until the run has been ingested, or if LangSmith is unreachable)."""
    try:
        from langsmith import Client

        client = Client()
        return client.get_run_url(run=client.read_run(run_id), project_name=langsmith_project())
    except Exception:
        return None


def trace_link(result: GenerationResult | None) -> None:
    if not result or not result.traced or not result.run_id:
        return
    url = langsmith_url(result.run_id)
    if url:
        st.link_button("Open trace in LangSmith", url)
    else:
        st.caption(f"LangSmith run id: `{result.run_id}` (link available once the trace is ingested)")


def coverage(req: Requirement, result: GenerationResult | None) -> float | None:
    return build_traceability(req, result.suite).coverage if result else None


# ---------- sidebar: choose and run ----------

reqs = requirements()
with st.sidebar:
    st.header("Requirement")
    rid = st.selectbox("Requirement", list(reqs), format_func=lambda r: f"{r} · {reqs[r].title}",
                       label_visibility="collapsed")
    req = reqs[rid]

    st.header("Run")
    has_key = get_settings().has_api_key
    if not has_key:
        st.warning("OPENAI_API_KEY is not set. Showing saved outputs only.")
    st.caption(f"Generation `{get_settings().generation_model}` · judge `{get_settings().judge_model}`")
    if tracing_enabled():
        st.caption(f"LangSmith tracing: **on** · project `{langsmith_project()}`")
    else:
        st.caption("LangSmith tracing: off (set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env`)")

    col1, col2 = st.columns(2)
    run_base = col1.button("Baseline", disabled=not has_key, width="stretch", help="1 LLM call")
    run_agt = col2.button("Agent", disabled=not has_key, width="stretch", type="primary",
                          help="5–9 LLM calls")
    run_eval = st.button("Evaluate both", disabled=not has_key, width="stretch",
                         help="DeepEval + Ragas + per-scenario verdicts (judge model)")

    if run_base:
        with st.spinner("Baseline: one prompt ..."):
            save_result(run_baseline(req))
        st.success("Baseline saved")
    if run_agt:
        with st.status("Agent running ...", expanded=True) as status:
            result = run_agent(req, kb=knowledge_base(),
                               on_step=lambda e: st.write(f"**{e['step']}**: {e['summary']}"))
            save_result(result)
            status.update(label=f"Agent finished: {len(result.suite.test_cases)} tests, "
                                f"{result.llm_calls} LLM calls, {result.elapsed_seconds:.0f}s", state="complete")
    if run_eval:
        with st.spinner("Evaluating saved outputs ..."):
            found = evaluate_requirement(req, default_judges())
            if found:
                update_reports(found)
                sent = send_feedback(found)
                st.success(f"Evaluated {len(found)} output(s)" + (f"; {sent} scores sent to LangSmith" if sent else ""))
            else:
                st.info("Generate outputs first.")

    st.divider()
    st.caption("CLI: `uv run python -m agentic_tcg.generate` then `uv run python -m agentic_tcg.evaluate --repeats 3`")

# ---------- header ----------

st.title("Agentic Test Case Generation")
st.caption("Credit-ratings prototype: a LangGraph agent with retrieval and a self-review loop, compared with a "
           "single-prompt baseline and evaluated with DeepEval and Ragas.")

results = {mode: load_result(mode, rid) for mode in MODES}
base, agent = results["baseline"], results["agent"]

st.subheader(f"{rid} · {req.title}")
cols = st.columns(4)


def metric(col, label, a, b, fmt="{:.0f}", inverse=False):
    value = fmt.format(a) if a is not None else "–"
    delta = None if a is None or b is None else fmt.format(a - b) + " vs baseline"
    col.metric(label, value, delta, delta_color="inverse" if inverse else "normal")


metric(cols[0], "Agent tests", len(agent.suite.test_cases) if agent else None,
       len(base.suite.test_cases) if base else None)
metric(cols[1], "Agent AC coverage", coverage(req, agent), coverage(req, base), fmt="{:.0%}")
metric(cols[2], "Agent LLM calls", agent.llm_calls if agent else None, base.llm_calls if base else None, inverse=True)
metric(cols[3], "Agent time (s)", agent.elapsed_seconds if agent else None,
       base.elapsed_seconds if base else None, inverse=True)

tabs = st.tabs(["Requirement", "Test cases", "Traceability", "Agent trace", "Evaluation", "Golden set"])

# ---------- requirement ----------

with tabs[0]:
    st.markdown(f"**Component:** {req.component}")
    st.info(req.user_story)
    st.markdown("**Acceptance criteria**")
    for ac in req.acceptance_criteria:
        st.markdown(f"- **{ac.id}**: {ac.text}")
    if req.references:
        st.caption("Related knowledge: " + ", ".join(req.references))
    for name, text in req.attachment_texts().items():
        with st.expander(f"Attachment: {name}"):
            st.code(text, language="yaml")

# ---------- test cases ----------

NO_OUTPUT = "No output yet. Use the sidebar, or run `uv run python -m agentic_tcg.generate -r {rid}`."

with tabs[1]:
    available = [m for m in MODES if results[m]] or list(MODES)
    mode = st.radio("Output", available, index=len(available) - 1, horizontal=True,
                    format_func=MODE_LABEL.get, key="mode")
    result = results[mode]
    if not result:
        st.info(NO_OUTPUT.format(rid=rid))
    else:
        suite = result.suite
        trace_link(result)
        fmt_tabs = st.tabs(["Table", "Gherkin", "pytest", "Clarification questions"])
        with fmt_tabs[0]:
            st.dataframe(pd.DataFrame(to_rows(suite)), width="stretch", hide_index=True)
            st.download_button("Download JSON", json.dumps(suite.model_dump(mode="json"), indent=2),
                               f"{rid}_{mode}.json", "application/json")
        with fmt_tabs[1]:
            feature = to_gherkin(req, suite)
            st.code(feature, language="gherkin")
            st.download_button("Download .feature", feature, f"{rid}_{mode}.feature")
        with fmt_tabs[2]:
            code = to_pytest(req, suite)
            st.code(code, language="python")
            st.download_button("Download pytest", code, f"test_{rid.lower()}_{mode}.py")
        with fmt_tabs[3]:
            st.markdown(questions_text(suite))

# ---------- traceability ----------

with tabs[2]:
    left, right = st.columns(2)
    for col, m in ((left, "baseline"), (right, "agent")):
        with col:
            st.markdown(f"**{MODE_LABEL[m]}**")
            if results[m]:
                trace = build_traceability(req, results[m].suite)
                st.metric("AC coverage", f"{trace.coverage:.0%}")
                st.markdown(traceability_markdown(trace))
                if trace.unknown_references:
                    st.warning("Unknown AC ids: " + ", ".join(trace.unknown_references))
            else:
                st.info("No output yet.")

# ---------- agent trace ----------

with tabs[3]:
    st.graphviz_chart(AGENT_GRAPH)
    if not agent:
        st.info(NO_OUTPUT.format(rid=rid))
    else:
        trace_link(agent)
        for i, entry in enumerate(agent.trace, 1):
            with st.expander(f"{i}. **{entry['step']}**: {entry['summary']}"):
                if entry.get("detail"):
                    st.json(entry["detail"], expanded=False)
        with st.expander(f"Retrieved knowledge ({len(agent.retrieved_contexts)} chunks)"):
            for chunk in agent.retrieved_contexts:
                st.text(chunk)

# ---------- evaluation ----------

with tabs[4]:
    records = [r for r in load_records() if r.requirement_id == rid]
    if not records:
        st.info("Not evaluated yet. Use **Evaluate both** in the sidebar, or run `uv run python -m agentic_tcg.evaluate`.")
    else:
        by_mode = {r.mode: r for r in records}
        names = list(dict.fromkeys(m.name for r in records for m in r.metrics))
        lower = {m.name for r in records for m in r.metrics if not m.higher_is_better}
        rows = []
        for name in names:
            b = by_mode["baseline"].score(name) if "baseline" in by_mode else None
            a = by_mode["agent"].score(name) if "agent" in by_mode else None
            rows.append({"Metric": name + (" (lower is better)" if name in lower else ""),
                         "Baseline": b, "Agent": a,
                         "Δ": None if a is None or b is None else a - b})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%.2f") for c in ("Baseline", "Agent", "Δ")})
        for r in records:
            with st.expander(f"Judge reasons: {MODE_LABEL[r.mode]}"):
                for m in r.metrics:
                    note = m.error or m.reason
                    if note:
                        st.markdown(f"- **{m.name}**: {note}")
    all_records = load_records()
    if all_records:
        with st.expander("Full report (all evaluated requirements)"):
            st.markdown(build_report(all_records))

# ---------- golden ----------

with tabs[5]:
    golden = load_golden(rid)
    st.caption("Reference test cases written by hand. The evaluation scores both generators against them.")
    st.dataframe(pd.DataFrame(to_rows(TestSuite(requirement_id=rid, test_cases=golden.test_cases))),
                 width="stretch", hide_index=True)
    st.markdown("**Expected ambiguities**")
    for a in golden.expected_ambiguities:
        st.markdown(f"- {a}")
    for ac, why in golden.untestable_acs.items():
        st.markdown(f"- **{ac}** is untestable as written: {why}")

st.caption(f"Outputs: `{config.OUTPUTS_DIR}` · Reports: `{config.REPORTS_DIR}`")
