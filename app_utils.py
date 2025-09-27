"""Utility helpers for parsing JSON columns and loading data sources."""
from __future__ import annotations

import io
import json
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import psycopg2
from pandas import json_normalize
from psycopg2 import sql


def try_parse_json(value: Any) -> Optional[Any]:
    """Return parsed JSON for strings that look like JSON, otherwise None."""
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate[0] not in "[{" or candidate[-1] not in "}]":
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def detect_json_columns(df: pd.DataFrame, sample_size: int = 50, threshold: float = 0.3) -> List[str]:
    """Heuristically detect columns that probably contain JSON strings."""
    candidates: List[str] = []
    for column in df.columns:
        series = df[column].dropna()
        if series.empty:
            continue
        sample = series.head(sample_size)
        parsed = sample.apply(try_parse_json)
        json_like_count = parsed.notna().sum()
        if json_like_count and json_like_count / len(sample) >= threshold:
            candidates.append(column)
    return candidates


def _flatten_single_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Expand dictionary rows into columns while keeping the original column intact."""
    parsed = df[column].apply(try_parse_json)
    dict_mask = parsed.apply(lambda item: isinstance(item, dict))
    list_mask = parsed.apply(lambda item: isinstance(item, list))

    expanded = df.copy()
    expanded[f"{column}__parsed"] = parsed

    if dict_mask.any():
        normalized = json_normalize(parsed[dict_mask])
        normalized.index = parsed[dict_mask].index
        normalized = normalized.add_prefix(f"{column}.")
        expanded = expanded.join(normalized, how="left")

    if list_mask.any():
        expanded[f"{column}__len"] = parsed.apply(lambda item: len(item) if isinstance(item, list) else None)

    return expanded


def flatten_json_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Flatten the requested JSON columns and merge the results."""
    flattened = df.copy()
    for column in columns:
        if column not in flattened.columns:
            continue
        flattened = _flatten_single_column(flattened, column)
    return flattened


def parse_table_identifier(table_name: str) -> List[str]:
    """Split schema-qualified table names into identifier parts."""
    if not table_name:
        raise ValueError("Table name is required")
    parts = [part.strip().strip('"') for part in table_name.split(".") if part.strip()]
    if not parts:
        raise ValueError("Table name is empty")
    return parts


def fetch_table_dataframe(conn_params: Dict[str, Any], table_name: str, limit: Optional[int]) -> pd.DataFrame:
    """Read a table from Greenplum/Postgres into a DataFrame."""
    identifier = parse_table_identifier(table_name)
    query = sql.SQL("SELECT * FROM {}" ).format(sql.Identifier(*identifier))
    params: List[Any] = []
    if limit and limit > 0:
        query = query + sql.SQL(" LIMIT %s")
        params.append(limit)

    filtered_params = {key: value for key, value in conn_params.items() if value not in (None, "")}

    with psycopg2.connect(**filtered_params) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            description = cursor.description or []

    columns = [getattr(col, "name", col[0]) for col in description]
    return pd.DataFrame(rows, columns=columns)


def load_uploaded_dataframe(uploaded_file: Any, sheet_name: Optional[str]) -> pd.DataFrame:
    """Load an Excel or CSV upload into a DataFrame."""
    suffix = uploaded_file.name.split(".")[-1].lower()
    buffer = io.BytesIO(uploaded_file.getvalue())

    if suffix in {"xlsx", "xls", "xlsm"}:
        return pd.read_excel(buffer, sheet_name=sheet_name)
    if suffix == "csv":
        buffer.seek(0)
        return pd.read_csv(buffer)
    raise ValueError(f"Unsupported file type: {suffix}")


__all__ = [
    "try_parse_json",
    "detect_json_columns",
    "flatten_json_columns",
    "parse_table_identifier",
    "fetch_table_dataframe",
    "load_uploaded_dataframe",
]
