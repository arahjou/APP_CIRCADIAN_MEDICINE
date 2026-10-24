"""Device-independent CSV boundary. No implicit conversion between activity units."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from io import StringIO
from typing import BinaryIO
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

SCHEMA_VERSION = "recording-1"
SIGNAL_UNITS = {
    "PIMn": "device PIM counts", "MELANOPIC EDI": "lx melanopic EDI",
    "WHITE LIGHT (LUX)": "lx photopic", "TEMPERATURE": "degC",
    "SLEEP_STATE": "0=wake, 1=sleep", "TATn": "device TAT counts",
    "ZCMn": "device ZCM counts",
}
ALIASES = {"Timestamp": "DATE/TIME", "timestamp": "DATE/TIME",
           "MelanopicEDI": "MELANOPIC EDI", "SLEEP/WAKE": "SLEEP_STATE"}


@dataclass(frozen=True)
class ImportOptions:
    timezone: str = "Europe/Berlin"
    date_order: str = "dayfirst"
    device: str = "unspecified"
    column_map: dict[str, str] = field(default_factory=dict)


@dataclass
class Recording:
    data: pd.DataFrame
    metadata: dict


def import_recording(source: BinaryIO, options: ImportOptions | None = None) -> Recording:
    """Read legacy/normalized CSV; reject ambiguous times and preserve missing signals.

    Mapping to PIMn explicitly asserts PIM counts; raw accelerometry needs a
    separately validated adapter. Naive DST overlaps/gaps require source correction.
    """
    options = options or ImportOptions()
    ZoneInfo(options.timezone)
    if options.date_order not in {"dayfirst", "monthfirst", "iso"}:
        raise ValueError("date_order must be dayfirst, monthfirst, or iso")
    source.seek(0)
    raw = source.read()
    source.seek(0)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    lines = text.splitlines()
    timestamp_names = {"DATE/TIME", "Timestamp", "timestamp"} | {
        key for key, value in options.column_map.items() if value == "DATE/TIME"
    }
    header = next((i for i, line in enumerate(lines[:50])
                   if any(name in line.replace('"', '').split(sep)
                          for sep in (",", ";", "\t") for name in timestamp_names)), None)
    if header is None:
        raise ValueError("No timestamp header in first 50 lines. Use DATE/TIME or Timestamp, or supply a column map.")
    separator = max((",", ";", "\t"), key=lines[header].count)
    df = pd.read_csv(StringIO("\n".join(lines[header:])), sep=separator)
    df.columns = [options.column_map.get(c, c).strip().replace(".", " ") for c in df.columns]
    df = df.rename(columns=ALIASES)
    if df.columns.duplicated().any():
        raise ValueError("Multiple source columns map to the same signal; select one explicitly.")
    if df.empty:
        raise ValueError("The recording contains no samples.")
    raw_ts = df["DATE/TIME"].astype(str).str.strip()
    has_offset = raw_ts.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True)
    if has_offset.any() and not has_offset.all():
        raise ValueError("Do not mix offset-bearing and naive timestamps.")
    parse_format = "ISO8601" if options.date_order == "iso" else "mixed"
    ts = pd.to_datetime(raw_ts, format=parse_format, errors="coerce",
                        dayfirst=options.date_order == "dayfirst", utc=bool(has_offset.all()))
    if ts.isna().any():
        raise ValueError(f"{int(ts.isna().sum())} invalid timestamps; check date order and source values.")
    try:
        ts = (ts.dt.tz_convert(options.timezone) if has_offset.all() else
              ts.dt.tz_localize(options.timezone, ambiguous="raise", nonexistent="raise"))
    except Exception as exc:
        raise ValueError("Ambiguous/nonexistent local time. Supply UTC offsets for daylight-saving transitions.") from exc
    if ts.duplicated().any():
        raise ValueError(f"{int(ts.duplicated().sum())} duplicate timestamps; resolve before analysis.")
    df["DATE/TIME"] = ts
    if not any(c in df for c in SIGNAL_UNITS):
        raise ValueError("No supported signal found. Supply PIMn, MELANOPIC EDI, TEMPERATURE, or SLEEP_STATE. Raw acceleration requires a validated adapter.")
    invalid_values = {}
    for col in SIGNAL_UNITS:
        if col not in df:
            continue
        original = df[col]
        values = pd.to_numeric(original, errors="coerce").astype(float)
        invalid = (~np.isfinite(values) & original.notna())
        if col == "SLEEP_STATE":
            invalid |= values.notna() & ~values.isin([0, 1])
        elif col != "TEMPERATURE":
            invalid |= values < 0
        invalid_values[col] = int(invalid.sum())
        df[col] = values.mask(invalid)
    reordered = not ts.is_monotonic_increasing
    df = df.sort_values("DATE/TIME").reset_index(drop=True)
    df["DATE"] = df["DATE/TIME"].dt.strftime("%Y-%m-%d")
    df["TIME"] = df["DATE/TIME"].dt.time
    df["HOUR"] = (df["DATE/TIME"].dt.hour + df["DATE/TIME"].dt.minute / 60
                  + df["DATE/TIME"].dt.second / 3600)
    df["Transition"] = df["DATE/TIME"].dt.tz_localize(None).dt.normalize()
    metadata = {
        "schema_version": SCHEMA_VERSION, "source_sha256": sha256(raw).hexdigest(),
        "source_name": str(getattr(source, "name", "uploaded.csv")),
        "import_options": asdict(options), "timezone": options.timezone,
        "units": {c: u for c, u in SIGNAL_UNITS.items() if c in df},
        "invalid_values": invalid_values, "sorted_input": reordered,
        "sleep_source": "provided" if "SLEEP_STATE" in df else "absent",
    }
    df.attrs["recording"] = metadata
    return Recording(df, metadata)
