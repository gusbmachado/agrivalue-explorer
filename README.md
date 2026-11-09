# AgriValue Explorer

A Streamlit application for exploring every CSV-backed production-value record in `data/` without loading the 563 MB fact table fully into memory. DuckDB scans the source lazily and powers global filters, metrics, time-series comparisons, pagination, and filtered exports.

## Run it

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL printed by Streamlit (normally `http://localhost:8501`).

## Notes

- Filters apply across all views.
- Values from different measures and currencies are not inherently additive; select a single measure for meaningful comparisons.
- The records view is paginated, and browser downloads are capped at 100,000 filtered rows.
- The original CSV files are only read; the application does not modify them.
