from __future__ import annotations

import json

import pytest

pytest.importorskip("langchain_ollama")
import tools.llm_conversation as lc


def test_pipeline_fallback_mode(tmp_path, monkeypatch):
    report = {
        "metadata": {"period_ids": ["A", "B"]},
        "sections": {"Sleep": {"Metrics": [{"Name": "SRI", "Period1": 60, "Period2": 40, "Difference": -20}]}}
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    class Boom:
        def invoke(self, _):
            raise RuntimeError("forced test failure")

    monkeypatch.setattr(lc, "_GRAPH", Boom())
    out = lc.get_intermediate_results(str(report_path))

    assert "final_report" in out
    assert "Fallback report" in out["final_report"]
    assert "error" in out
