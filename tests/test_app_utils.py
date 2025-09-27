import io
from typing import Any

import pandas as pd
import pytest

import app_utils


class DummyUpload:
    def __init__(self, name: str, data: bytes) -> None:
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def test_try_parse_json_handles_dicts_lists_and_invalid():
    assert app_utils.try_parse_json('{"a": 1}') == {"a": 1}
    assert app_utils.try_parse_json('[1, 2]') == [1, 2]
    assert app_utils.try_parse_json('{invalid}') is None
    assert app_utils.try_parse_json(42) is None
    assert app_utils.try_parse_json("   ") is None


def test_detect_json_columns_returns_candidate_columns():
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "meta": ['{"foo": "bar"}', '{"foo": "baz"}', "not json"],
            "notes": ["hello", "world", "!"]
        }
    )
    detected = app_utils.detect_json_columns(df, sample_size=3, threshold=0.3)
    assert detected == ["meta"]


def test_flatten_json_columns_expands_dicts_and_lists():
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "payload": [
                '{"user": {"name": "Ana"}}',
                '[{"item": 1}, {"item": 2}]',
                "not-json"
            ],
        }
    )
    flattened = app_utils.flatten_json_columns(df, ["payload"])

    assert "payload__parsed" in flattened
    assert flattened.loc[0, "payload.user.name"] == "Ana"
    assert flattened.loc[1, "payload__len"] == 2
    assert pd.isna(flattened.loc[2, "payload__parsed"])


@pytest.mark.parametrize(
    "identifier, parts",
    [
        ("public.my_table", ["public", "my_table"]),
        ("my_table", ["my_table"]),
        ('"Case"."Sensitive"', ["Case", "Sensitive"]),
    ],
)
def test_parse_table_identifier(identifier: str, parts: list[str]):
    assert app_utils.parse_table_identifier(identifier) == parts


@pytest.mark.parametrize("value", ["", " ", ".", "..table"])
def test_parse_table_identifier_rejects_invalid(value: str):
    with pytest.raises(ValueError):
        app_utils.parse_table_identifier(value)


def test_fetch_table_dataframe_uses_connection_and_limit(monkeypatch):
    executed: dict[str, Any] = {}

    class DummyCursor:
        description = [
            type("Col", (), {"name": "id"})(),
            type("Col", (), {"name": "payload"})(),
        ]

        def __enter__(self) -> "DummyCursor":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def execute(self, query, params):
            executed["query_type"] = type(query).__name__
            executed["params"] = list(params)

        def fetchall(self):
            return [(1, {"a": 1}), (2, {"b": 2})]

    class DummyConnection:
        def __enter__(self) -> "DummyConnection":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def cursor(self) -> DummyCursor:
            return DummyCursor()

    def fake_connect(**kwargs):
        executed["connect_kwargs"] = kwargs
        return DummyConnection()

    monkeypatch.setattr(app_utils.psycopg2, "connect", fake_connect)

    df = app_utils.fetch_table_dataframe(
        {"host": "db", "port": 5432, "dbname": "test", "user": "u", "password": "p"},
        "public.events",
        limit=5,
    )

    assert df.to_dict("records") == [
        {"id": 1, "payload": {"a": 1}},
        {"id": 2, "payload": {"b": 2}},
    ]
    assert executed["connect_kwargs"]["host"] == "db"
    assert executed["params"] == [5]


@pytest.mark.parametrize("suffix,data_loader", [
    ("csv", lambda df: df.to_csv(index=False).encode("utf-8")),
    ("xlsx", lambda df: _dataframe_to_xlsx_bytes(df)),
])
def test_load_uploaded_dataframe_supports_csv_and_excel(suffix: str, data_loader):
    df = pd.DataFrame({"id": [1, 2], "value": ["a", "b"]})
    payload = data_loader(df)
    uploaded = DummyUpload(f"test.{suffix}", payload)

    result = app_utils.load_uploaded_dataframe(uploaded, sheet_name=None)
    assert result.equals(df)


def _dataframe_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buffer.getvalue()


def test_load_uploaded_dataframe_rejects_unknown_extension():
    uploaded = DummyUpload("data.txt", b"text")
    with pytest.raises(ValueError):
        app_utils.load_uploaded_dataframe(uploaded, sheet_name=None)
