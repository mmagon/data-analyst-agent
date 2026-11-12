import csv
import io
import statistics
from typing import Any

from mistralai import agents


def _split_rows(csv_text: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    if not csv_text or not csv_text.strip():
        raise agents.ToolError("csv_text is empty; paste CSV content including a header row.")
    raw = list(enumerate(csv.reader(io.StringIO(csv_text)), start=1))
    raw = [(line, row) for line, row in raw if any(cell.strip() for cell in row)]
    if len(raw) < 2:
        raise agents.ToolError("csv_text has a header but no data rows.")
    return raw[0][1], raw[1:]


def validate_csv_text(csv_text: str) -> dict[str, Any]:
    """Validate pasted CSV text: header, row and column counts, and structural issues."""
    header, data = _split_rows(csv_text)
    ncols = len(header)
    issues: list[str] = []
    empty_cells = [i + 1 for i, name in enumerate(header) if not name.strip()]
    if empty_cells:
        issues.append(f"empty header cell(s) at column position(s) {empty_cells}")
    seen: list[str] = []
    dupes: list[str] = []
    for name in header:
        if name.strip() and name in seen and name not in dupes:
            dupes.append(name)
        seen.append(name)
    if dupes:
        issues.append(f"duplicate header name(s): {dupes}")
    ragged = [{"line": line, "cells": len(row)} for line, row in data if len(row) != ncols]
    if ragged:
        issues.append(f"ragged row(s) with a cell count != {ncols}: {ragged}")
    return {
        "ok": not issues,
        "columns": ncols,
        "data_rows": len(data),
        "header": header,
        "issues": issues,
    }


def summarize_csv_text(csv_text: str, max_rows: int = 50000) -> dict[str, Any]:
    """Summarize pasted CSV text: per-column type, missing counts, and numeric min/max/mean/median."""
    validation = validate_csv_text(csv_text)
    if validation["data_rows"] > max_rows:
        raise agents.ToolError(
            f"too many data rows ({validation['data_rows']} > max_rows={max_rows}); "
            "summarize in chunks or pass a larger max_rows."
        )
    header, data = _split_rows(csv_text)
    columns: list[dict[str, Any]] = []
    for idx, name in enumerate(header):
        values = [cells[idx].strip() if idx < len(cells) else "" for _line, cells in data]
        missing = sum(1 for v in values if not v)
        present = [v for v in values if v]
        col: dict[str, Any] = {
            "name": name or f"column_{idx + 1}",
            "missing": missing,
            "non_missing": len(present),
        }
        numbers: list[float] = []
        numeric = True
        for v in present:
            try:
                numbers.append(float(v))
            except ValueError:
                numeric = False
                break
        if numeric and numbers:
            col["type"] = "number"
            col["min"] = min(numbers)
            col["max"] = max(numbers)
            col["mean"] = statistics.fmean(numbers)
            col["median"] = statistics.median(numbers)
        else:
            col["type"] = "text"
            col["distinct"] = len(set(present))
        columns.append(col)
    return {
        "rows": validation["data_rows"],
        "columns": validation["columns"],
        "column_summaries": columns,
        "validation": validation,
    }


_READ_ONLY = agents.ToolAnnotations(read_only_hint=True)

validate_csv = agents.tool(
    name="validate_csv",
    model_access="direct",
    annotations=_READ_ONLY,
)(validate_csv_text)

summarize_csv = agents.tool(
    name="summarize_csv",
    model_access="direct",
    annotations=_READ_ONLY,
)(summarize_csv_text)
