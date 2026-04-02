from __future__ import annotations

import uuid
from typing import Callable, Dict, Any

from tools.llm_conversation import get_intermediate_results
from tools.app_logging import log_event


def run_ai_pipeline(
    *,
    json_filepath: str,
    model: str,
    audience: str,
    anamnesis: str,
    progress_callback: Callable[[str], None] | None,
) -> tuple[str, Dict[str, Any]]:
    run_id = uuid.uuid4().hex[:12]
    log_event("ai_pipeline_start", run_id=run_id, model=model, audience=audience)
    results = get_intermediate_results(
        json_filepath,
        model=model,
        audience=audience,
        anamnesis=anamnesis,
        progress_callback=progress_callback,
    )
    if "error" in results:
        log_event("ai_pipeline_error", run_id=run_id, error=results["error"])
    else:
        log_event(
            "ai_pipeline_complete",
            run_id=run_id,
            evidence_count=len(results.get("evidence_items") or []),
        )
    return run_id, results
