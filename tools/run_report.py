"""Strict JSON and standalone, escaped research reports; no LLM dependency."""
from __future__ import annotations

import html
import json
import math
from datetime import date, datetime, time

import numpy as np
import pandas as pd


def json_safe(value):
    if isinstance(value, pd.DataFrame):
        return json_safe(value.to_dict("records"))
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (datetime, date, time, pd.Timestamp)):
        return value.isoformat()
    return value


def render_run_report(run: dict) -> str:
    """Self-contained HTML with quality, methods, metrics and daily signal plots."""
    def esc(value):
        return html.escape(str(value))
    parts = ["<!doctype html><html><head><meta charset='utf-8'><title>CMAS research report</title>",
             "<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#183040}table{border-collapse:collapse;display:block;overflow:auto;margin:16px 0}td,th{border:1px solid #ccd8df;padding:7px;text-align:left}th{background:#edf4f8}pre{white-space:pre-wrap}svg{max-width:100%;height:auto}h2{margin-top:32px}</style></head><body>",
             f"<h1>CMAS research report — {esc(run['record_id'])}</h1>",
             "<p>Research use. Descriptive measurements; no diagnosis or treatment recommendation.</p>",
             f"<p>{esc(run['description'])}</p><p>Run: {esc(run['run_id'])} · Status: {esc(run['status'])}</p>",
             "<h2>Recording and quality</h2>",
             f"<p>Local timezone: {esc(run['metadata'].get('timezone'))}. Selected dates: {esc(', '.join(run['selected_dates']))}</p>"]
    quality = run["quality"]
    parts.append(pd.DataFrame(quality["signals"]).T.to_html(escape=True))
    for message in quality["warnings"] + quality["errors"]:
        parts.append(f"<p>{esc(message)}</p>")
    parts.append("<h2>Daily signal overview</h2><p>Means of observed samples; missing days are omitted, not interpolated.</p>")
    for signal, rows in run["daily_signals"].items():
        values = [r["mean"] for r in rows if r["mean"] is not None]
        parts.append(f"<h3>{esc(signal)} ({esc(run['metadata'].get('units', {}).get(signal, 'source units'))})</h3>")
        if values:
            low, high = min(values), max(values)
            marks = []
            for i, row in enumerate(rows):
                if row["mean"] is None:
                    continue
                x = 45 + i * 650 / max(len(rows) - 1, 1)
                y = 130 - (row["mean"] - low) * 100 / (high - low or 1)
                marks.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='4' fill='#147b88'><title>{esc(row['date'])}: {row['mean']:.3g}</title></circle>")
            parts.append(f"<svg viewBox='0 0 760 175' role='img' aria-label='{esc(signal)} daily means'><path d='M40 20 V140 H720' fill='none' stroke='#789'/><text x='45' y='165'>{esc(rows[0]['date'])}</text><text x='620' y='165'>{esc(rows[-1]['date'])}</text>{''.join(marks)}</svg>")
        parts.append(pd.DataFrame(rows).to_html(index=False, escape=True))
    parts.append("<h2>Calculated metrics</h2>")
    parts.append("<p>Sleep durations and exposure durations: minutes. Phase and CPD: hours. "
                 "SRI: index points; coverage: percent; IS, IV and RA: dimensionless. "
                 "Activity L5/M10, mesor and amplitude retain device PIM units; corresponding "
                 "light values retain melanopic EDI lux. Day-level signal means are descriptive, "
                 "not clinical reference ranges.</p>")
    for name, result in run["metrics"].items():
        parts.append(f"<h3>{esc(name)} — {esc(result['status'])}</h3>")
        if result.get("reason"):
            parts.append(f"<p>{esc(result['reason'])}</p>")
        data = result.get("data")
        if isinstance(data, list) and data:
            parts.append(pd.DataFrame(data).to_html(index=False, escape=True, na_rep="Unavailable"))
        elif data:
            parts.append(f"<pre>{esc(json.dumps(data, indent=2))}</pre>")
    parts.append("<h2>Methods and provenance</h2>")
    parts.append(f"<pre>{esc(json.dumps({'parameters': run['parameters'], 'metadata': run['metadata'], 'software': run['software']}, indent=2))}</pre>")
    parts.append("</body></html>")
    return "".join(parts)
