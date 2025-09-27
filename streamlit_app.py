"""Streamlit frontend for exploring JSON-heavy datasets."""
from __future__ import annotations

import io
from typing import Optional

import pandas as pd
import streamlit as st

from app_utils import (
    detect_json_columns,
    fetch_table_dataframe,
    flatten_json_columns,
    load_uploaded_dataframe,
)


def main() -> None:
    """Render the Streamlit UI for browsing JSON columns."""
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


if __name__ == "__main__":  # pragma: no cover - executed only by Streamlit runtime
    main()
