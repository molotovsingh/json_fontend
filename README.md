# Excel JSON Column Explorer

Small Streamlit helper to browse Excel/CSV files or Greenplum/Postgres tables that contain JSON fields.

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
4. Use the sidebar to upload your Excel/CSV file **or** enter your Greenplum/Postgres credentials and table name, then select the columns that should be parsed as JSON.

## Database mode

- Fill in the host, port, database, user, password, and the table name (e.g. `public.my_table`).
- Optionally set a row limit to keep the preview lightweight; set it to `0` to grab the full table.
- Press **Load table** to fetch the data; the JSON parsing controls work the same as they do for file uploads.

## How it helps

- Automatically suggests columns that look like JSON by sampling the data.
- Expands dict-like JSON into top-level columns while keeping the raw column around.
- Adds helper columns for list-like JSON so you can see row-by-row counts.
- Lets you preview the raw and flattened tables, then download the transformed data as CSV.

## Extending

- Adjust the heuristics in `detect_json_columns` if your data uses different hints (e.g. fixed prefixes).
- Update `_flatten_single_column` to normalize lists if you want to explode them into multiple rows.
- Add domain-specific validation or summary stats with extra Streamlit widgets.
