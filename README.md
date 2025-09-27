# json_fontend

Makes your (Greenplum/Postgres) JSON columns readable from a friendly Streamlit frontend. Also works with Excel/CSV uploads that carry JSON blobs.

## Quick start

1. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Launch the app:
   ```bash
   streamlit run streamlit_app.py
   ```
4. Use the sidebar to upload your Excel/CSV file or enter your Greenplum/Postgres credentials and table name, then choose the columns that should be parsed as JSON.

## Database mode

- Fill in host, port, database, user, password, and the table name (e.g. `public.my_table`).
- Optionally cap the preview with a row limit (set `0` to fetch the full table).
- Press **Load table** to query the database; the JSON parsing workflow matches the upload experience.

## What you get

- Heuristic detection of columns that look like JSON content.
- Flattened dictionary fields surfaced as top-level columns while keeping the original JSON parsed alongside.
- List columns augmented with a length helper to show counts per row.
- Ability to preview the raw/flattened data and download the transformed result as CSV.

## Extending

- Tweak `detect_json_columns` if you want different heuristics (e.g. regex-based matching).
- Adjust `_flatten_single_column` to explode list columns into multiple rows when needed.
- Layer in domain-specific validation or summaries with extra Streamlit widgets.
