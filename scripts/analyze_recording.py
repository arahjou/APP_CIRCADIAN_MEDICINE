"""Run the same numerical workflow as Streamlit, without an LLM or web server."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.recording_service import analyze_recording, persist_recording_run
from tools.recording import ImportOptions, import_recording


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--timezone", default="Europe/Berlin")
    parser.add_argument("--date-order", choices=["dayfirst", "monthfirst", "iso"], default="dayfirst")
    parser.add_argument("--device", default="unspecified")
    parser.add_argument("--column-map", default="{}", help="JSON source-to-canonical header mapping")
    parser.add_argument("--dates", nargs="+")
    parser.add_argument("--out", type=Path, default=Path("analysis_runs"))
    parser.add_argument("--db", help="Optional SQLite path; omitted means artifacts only")
    args = parser.parse_args()
    try:
        with args.input.open("rb") as source:
            recording = import_recording(source, ImportOptions(args.timezone, args.date_order, args.device, json.loads(args.column_map)))
        result = analyze_recording(recording, record_id=args.record_id,
                                   description=args.description, selected_dates=args.dates)
        db = None
        if args.db:
            from tools.database import ActigraphDB
            db = ActigraphDB(args.db)
        directory = persist_recording_run(result, output_dir=args.out, db=db)
        print(f"{result['report']['status']}: {directory / 'report.html'}")
        return 2 if result["report"]["status"] == "partial" else 0
    except Exception as exc:
        parser.exit(1, f"Analysis failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
