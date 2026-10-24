import json

from langchain_core.messages import AIMessage, HumanMessage

from src.graph.trace import append_eval_trace_line, build_eval_trace_record


def test_eval_trace_row_matches_required_shape_masks_pii_and_appends_jsonl(tmp_path):
    state = {
        "messages": [
            HumanMessage(content="Tư vấn cho tôi, SĐT 0901234567"),
            AIMessage(content="Sản phẩm giá 1.000.000đ, phù hợp anh nhé?"),
        ],
        "call_brief": {"profile_facts": {"budget_vnd": 2_000_000}},
    }
    context = {
        "config": "full",
        "scenario_id": "SC-TEST-01",
        "call": "call_2",
        "turn": 1,
        # For a non-streamed model, this is measured by the harness as the
        # first point at which a complete response becomes available.
        "ttft_ms": 420,
        "customer_input_mode": "clean",
    }

    record = build_eval_trace_record(
        state=state, run_id="run-test", total_ms=450, context=context
    )
    target = tmp_path / "trace.jsonl"
    append_eval_trace_line(record, target)

    written = json.loads(target.read_text(encoding="utf-8").strip())
    assert written["run_id"] == "run-test"
    assert written["config"] == "full"
    assert written["call"] == "call_2"
    assert written["latency"] == {"ttft_ms": 420, "total_ms": 450}
    assert "0901234567" not in json.dumps(written, ensure_ascii=False)
    assert written["questions"][0]["type"] == "open"
    assert written["claims"][0]["value"] == 1_000_000


def test_eval_trace_requires_real_context_fields():
    import pytest
    from pydantic import ValidationError

    from src.graph.trace import _EvalTraceLine

    with pytest.raises(ValidationError):
        _EvalTraceLine.model_validate({"run_id": "incomplete"})
