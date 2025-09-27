import io
import json
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import psycopg2
import streamlit as st
from pandas import json_normalize
from psycopg2 import sql


def _try_parse_json(value: Any) -> Optional[Any]:
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
        parsed = sample.apply(_try_parse_json)
        json_like_count = parsed.notna().sum()
        if json_like_count and json_like_count / len(sample) >= threshold:
            candidates.append(column)
    return candidates


def _flatten_single_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Expand dictionary rows into columns while keeping the original column intact."""
    parsed = df[column].apply(_try_parse_json)
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


st.set_page_config(page_title="Excel JSON Viewer", layout="wide")
st.title("Excel JSON Column Explorer")

source = st.sidebar.radio(
    "Load data via",
    options=("Upload file", "Database table"),
)

df: Optional[pd.DataFrame] = None
source_label: Optional[str] = None

if source == "Upload file":
    st.sidebar.subheader("Upload")
    uploaded = st.sidebar.file_uploader(
        "Excel or CSV",
        type=["xlsx", "xls", "xlsm", "csv"],
    )

    if uploaded:
        suffix = uploaded.name.split(".")[-1].lower()
        sheet: Optional[str] = None
        if suffix in {"xlsx", "xls", "xlsm"}:
            workbook = pd.ExcelFile(io.BytesIO(uploaded.getvalue()))
            sheet = st.sidebar.selectbox("Sheet", workbook.sheet_names)

        try:
            df = load_uploaded_dataframe(uploaded, sheet)
            source_label = f"File `{uploaded.name}`"
        except Exception as exc:  # pragma: no cover - surfaced in UI
            st.error(f"Failed to load file: {exc}")
else:
    st.sidebar.subheader("Connection")
    with st.sidebar.form("db_form"):
        host = st.text_input("Host", value="localhost")
        port = st.number_input("Port", value=5432, step=1)
        database = st.text_input("Database")
        user = st.text_input("User")
        password = st.text_input("Password", type="password")
        table_name = st.text_input("Table (schema.table)")
        limit = st.number_input("Row limit (0 = unlimited)", min_value=0, value=1000, step=100)
        submitted = st.form_submit_button("Load table")

    if submitted:
        required = {
            "Host": host,
            "Database": database,
            "User": user,
            "Table": table_name,
        }
        missing = [label for label, value in required.items() if not value]
        if missing:
            st.sidebar.error(f"Provide values for: {', '.join(missing)}")
        else:
            connection_kwargs = {
                "host": host,
                "port": int(port),
                "dbname": database,
                "user": user,
                "password": password,
            }
            bounded_limit = int(limit) if limit and limit > 0 else None
            try:
                with st.spinner("Loading table..."):
                    table_df = fetch_table_dataframe(connection_kwargs, table_name.strip(), bounded_limit)
                st.session_state["db_df"] = table_df
                st.session_state["db_table"] = table_name.strip()
                st.sidebar.success(f"Loaded {len(table_df)} rows")
            except Exception as exc:  # pragma: no cover - surfaced in UI
                st.sidebar.error(f"Failed to load table: {exc}")

    if "db_df" in st.session_state:
        df = st.session_state["db_df"]
        table_display = st.session_state.get("db_table", "table")
        source_label = f"Table `{table_display}`"

if df is not None:
    if source_label:
        st.caption(f"Data source: {source_label}")

    st.subheader("Raw Preview")
    st.dataframe(df.head(100), use_container_width=True)

    detected = detect_json_columns(df)
    st.sidebar.markdown("---")
    st.sidebar.subheader("JSON Columns")
    suggestions = st.sidebar.multiselect(
        "Columns that should be parsed",
        options=df.columns.tolist(),
        default=detected,
    )

    if suggestions:
        flattened_df = flatten_json_columns(df, suggestions)
        st.subheader("Flattened Result")
        st.caption("Dictionary fields are expanded, lists show up with a length helper column.")
        st.dataframe(flattened_df, use_container_width=True)

        csv_bytes = flattened_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download as CSV",
            data=csv_bytes,
            file_name="flattened_output.csv",
            mime="text/csv",
        )

        with st.expander("Column notes"):
            st.markdown(
                "- The original JSON column is preserved as `column__parsed`\n"
                "- Nested dictionary keys become `column.key` columns\n"
                "- Lists get an extra `column__len` helper showing item counts"
            )
    else:
        st.info("Select at least one column in the sidebar to parse JSON content.")
else:
    if source == "Upload file":
        st.info("Upload an Excel or CSV file from the sidebar to get started.")
    else:
        st.info("Fill in the connection details and load a Greenplum table to inspect its JSON columns.")
