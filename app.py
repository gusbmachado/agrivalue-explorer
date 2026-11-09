from __future__ import annotations

import math
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
FACT_FILE = DATA_DIR / "Value_of_Production_E_All_Data_(Normalized).csv"
AREA_FILE = DATA_DIR / "Value_of_Production_E_AreaCodes.csv"
ITEM_FILE = DATA_DIR / "Value_of_Production_E_ItemCodes.csv"
ELEMENT_FILE = DATA_DIR / "Value_of_Production_E_Elements.csv"
FLAG_FILE = DATA_DIR / "Value_of_Production_E_Flags.csv"
PAGE_SIZE = 100
DOWNLOAD_LIMIT = 100_000


st.set_page_config(
    page_title="AgriValue Explorer",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .stApp { background: #f5f2e9; color: #17362a; }
      [data-testid="stSidebar"] { background: #17362a; }
      [data-testid="stSidebar"] * { color: #f8f5ec; }
      [data-testid="stMetric"] {
        background: #fffdf7; border: 1px solid #ded8c9; border-radius: 14px;
        padding: 16px 18px; box-shadow: 0 4px 18px rgba(35, 58, 45, .05);
      }
      .eyebrow { color: #b4562a; font-weight: 700; letter-spacing: .14em; font-size: .76rem; }
      .hero-title { font-size: clamp(2.1rem, 4vw, 4.2rem); line-height: .98; margin: .35rem 0 .8rem; }
      .hero-copy { color: #557064; max-width: 760px; font-size: 1.05rem; }
      .data-note { color: #6f796f; font-size: .82rem; }
      div[data-testid="stPlotlyChart"] { background: #fffdf7; border-radius: 14px; }
      .stTabs [data-baseweb="tab-list"] { gap: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


@st.cache_resource(show_spinner="Preparing the data engine…")
def database() -> duckdb.DuckDBPyConnection:
    if not FACT_FILE.exists():
        raise FileNotFoundError(f"Missing data file: {FACT_FILE}")
    con = duckdb.connect(database=":memory:")
    con.execute("SET threads TO 4")
    con.execute(
        f"""
        CREATE VIEW production AS
        SELECT
          "Area Code"::INTEGER AS area_code,
          "Area Code (M49)"::VARCHAR AS m49_code,
          Area,
          "Item Code"::INTEGER AS item_code,
          "Item Code (CPC)"::VARCHAR AS cpc_code,
          Item,
          "Element Code"::INTEGER AS element_code,
          Element,
          Year::INTEGER AS production_year,
          Unit,
          Value::DOUBLE AS value,
          Flag
        FROM read_csv('{sql_path(FACT_FILE)}', header=true, auto_detect=true)
        """
    )
    return con


@st.cache_data(show_spinner=False)
def dimensions() -> tuple[list[str], list[str], list[str], dict[str, str]]:
    areas = pd.read_csv(AREA_FILE)["Area"].dropna().sort_values().tolist()
    items = pd.read_csv(ITEM_FILE)["Item"].dropna().sort_values().tolist()
    elements = pd.read_csv(ELEMENT_FILE)["Element"].dropna().sort_values().tolist()
    flags_df = pd.read_csv(FLAG_FILE, skipinitialspace=True)
    flags_df.columns = flags_df.columns.str.strip()
    flags = dict(zip(flags_df["Flag"], flags_df["Description"]))
    return areas, items, elements, flags


def in_clause(column: str, values: list[str], clauses: list[str], params: list[object]) -> None:
    if values:
        clauses.append(f'{column} IN ({", ".join("?" for _ in values)})')
        params.extend(values)


def query_df(sql: str, params: list[object] | None = None) -> pd.DataFrame:
    return database().execute(sql, params or []).fetchdf()


try:
    areas, items, elements, flag_labels = dimensions()
except (FileNotFoundError, KeyError) as exc:
    st.error(f"The data folder is incomplete or has an unexpected schema: {exc}")
    st.stop()

with st.sidebar:
    st.markdown("## 🌾 AgriValue")
    st.caption("FAOSTAT production value explorer")
    st.markdown("---")
    st.markdown("#### Focus the dataset")
    selected_areas = st.multiselect("Areas", areas, placeholder="All areas")
    selected_items = st.multiselect("Products", items, placeholder="All products")
    selected_elements = st.multiselect("Measures", elements, placeholder="All measures")
    years = st.slider("Year range", 1961, 2024, (2000, 2024))
    selected_flags = st.multiselect(
        "Data status",
        list(flag_labels),
        format_func=lambda code: f"{code} · {flag_labels[code]}",
        placeholder="All statuses",
    )
    st.markdown("---")
    st.caption("Filters apply to every metric, chart, table, and export.")

clauses = ["production_year BETWEEN ? AND ?"]
params: list[object] = [years[0], years[1]]
in_clause("Area", selected_areas, clauses, params)
in_clause("Item", selected_items, clauses, params)
in_clause("Element", selected_elements, clauses, params)
in_clause("Flag", selected_flags, clauses, params)
where_sql = " AND ".join(clauses)

st.markdown('<div class="eyebrow">GLOBAL AGRICULTURE · 1961–2024</div>', unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">The value behind<br>what the world grows.</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="hero-copy">Explore the complete production-value collection by place, product, measure, and year. The source stays on disk; only the answers you ask for enter memory.</p>',
    unsafe_allow_html=True,
)

try:
    with st.spinner("Reading the selected slice…"):
        summary = query_df(
            f"""
            SELECT count(*) AS records, sum(value) AS total_value,
                   avg(value) AS average_value, count(DISTINCT Area) AS areas
            FROM production WHERE {where_sql}
            """,
            params,
        ).iloc[0]
except Exception as exc:
    st.error(f"Could not query the production file: {exc}")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Records", f"{int(summary['records']):,}")
c2.metric("Total value", f"{summary['total_value']:,.0f}" if pd.notna(summary["total_value"]) else "—")
c3.metric("Average value", f"{summary['average_value']:,.1f}" if pd.notna(summary["average_value"]) else "—")
c4.metric("Areas represented", f"{int(summary['areas']):,}")
st.caption("Values are shown in their source units. Avoid summing unlike measures or currencies; use the Measure filter for comparable totals.")

overview_tab, compare_tab, records_tab, guide_tab = st.tabs(
    ["Overview", "Compare", "Records", "Data guide"]
)

with overview_tab:
    left, right = st.columns((1.8, 1), gap="large")
    with left:
        st.subheader("Value over time")
        trend = query_df(
            f"SELECT production_year AS Year, sum(value) AS Value FROM production WHERE {where_sql} GROUP BY production_year ORDER BY production_year",
            params,
        ).set_index("Year")
        st.line_chart(trend, color="#b4562a", height=390)
    with right:
        st.subheader("Top products")
        top_items = query_df(
            f"""SELECT Item, sum(value) AS Value FROM production WHERE {where_sql}
                GROUP BY Item ORDER BY Value DESC NULLS LAST LIMIT 12""",
            params,
        ).set_index("Item")
        st.bar_chart(top_items, color="#3d7456", horizontal=True, height=390)

with compare_tab:
    st.subheader("Compare places or products")
    group_label = st.radio("Group the timeline by", ["Area", "Item", "Element"], horizontal=True)
    top_n = st.slider("Number of series", 3, 15, 8)
    safe_group = {"Area": "Area", "Item": "Item", "Element": "Element"}[group_label]
    comparison = query_df(
        f"""
        WITH ranked AS (
          SELECT {safe_group} AS series, sum(value) AS total
          FROM production WHERE {where_sql}
          GROUP BY {safe_group} ORDER BY total DESC NULLS LAST LIMIT {int(top_n)}
        )
        SELECT p.production_year AS Year, p.{safe_group} AS series, sum(p.value) AS Value
        FROM production p JOIN ranked r ON p.{safe_group} = r.series
        WHERE {where_sql}
        GROUP BY p.production_year, p.{safe_group} ORDER BY p.production_year
        """,
        params + params,
    )
    if comparison.empty:
        st.info("No comparable series match these filters.")
    else:
        st.line_chart(comparison, x="Year", y="Value", color="series", height=500)

with records_tab:
    st.subheader("Underlying records")
    total_rows = int(summary["records"])
    max_page = max(1, math.ceil(total_rows / PAGE_SIZE))
    page = st.number_input("Page", min_value=1, max_value=max_page, value=1, step=1)
    offset = (int(page) - 1) * PAGE_SIZE
    records = query_df(
        f"""
        SELECT Area, Item, Element, production_year AS Year, Unit, value AS Value, Flag,
               area_code AS "Area code", item_code AS "Item code"
        FROM production WHERE {where_sql}
        ORDER BY production_year DESC, Area, Item LIMIT {PAGE_SIZE} OFFSET {offset}
        """,
        params,
    )
    st.dataframe(records, use_container_width=True, hide_index=True, height=520)
    st.caption(f"Page {int(page):,} of {max_page:,} · {PAGE_SIZE} rows per page")

    export = query_df(
        f"""
        SELECT Area, Item, Element, production_year AS Year, Unit, value AS Value, Flag
        FROM production WHERE {where_sql} ORDER BY production_year, Area, Item LIMIT {DOWNLOAD_LIMIT}
        """,
        params,
    )
    st.download_button(
        "Download filtered CSV",
        export.to_csv(index=False).encode("utf-8"),
        "agrivalue_filtered.csv",
        "text/csv",
        help=f"Exports up to {DOWNLOAD_LIMIT:,} matching records.",
    )
    if total_rows > DOWNLOAD_LIMIT:
        st.caption(f"Export capped at {DOWNLOAD_LIMIT:,} of {total_rows:,} records for browser reliability.")

with guide_tab:
    st.subheader("What is in this collection?")
    st.markdown(
        """
        Each record identifies an **area**, **agricultural product**, **production-value measure**,
        **year**, **unit**, numeric **value**, and provenance **flag**. The supporting code sheets in
        `data/` provide the canonical area, item, element, and flag labels.

        Aggregates and individual countries can both appear as areas. Likewise, the measures include
        current and constant values in local currency, US dollars, and international dollars. Select
        one measure before making direct comparisons or interpreting totals.
        """
    )
    flag_table = pd.DataFrame(flag_labels.items(), columns=["Flag", "Meaning"])
    st.dataframe(flag_table, hide_index=True, use_container_width=True)
    st.markdown('<p class="data-note">Source files are read directly from the project’s data directory. No source rows are modified.</p>', unsafe_allow_html=True)
