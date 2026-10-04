"""
community_insights.py
Connects the Streamlit discovery engine to the n8n "Photo Retrieval Discovery" workflow.

- Reads tagged threads from the Google Sheet tab `insights` (written by n8n)
- Triggers a new n8n run through its webhook
- Renders charts, filters, cue analysis and verbatim quotes

Usage in your app:
    from community_insights import render_community_insights
    render_community_insights()          # e.g. inside a st.tabs(...) block

Secrets (.streamlit/secrets.toml locally, or the Secrets panel on Streamlit Cloud):
    N8N_WEBHOOK_URL = "https://<your-n8n>/webhook/photo-discovery"
    INSIGHTS_SHEET_URL = "https://docs.google.com/spreadsheets/d/<id>/edit"   # sheet shared: Anyone with the link → Viewer
    N8N_WEBHOOK_KEY = "..."   # optional, only if the n8n webhook uses Header Auth (X-Api-Key)
    # A service account ([connections.gsheets] block) also works but is no longer required.

Fallback: if the sheet can't be reached, it loads data/insights_seed.csv
(export your `insights` tab there before a demo).
"""
from __future__ import annotations

import io
import re
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import pandas as pd
import requests
import streamlit as st

COLUMNS = [
    "source", "url", "title", "is_retrieval_problem", "photo_type", "intent",
    "cues_remembered", "cues_forgotten", "query_tried", "failure_stage",
    "workaround", "key_quote", "summary", "scraped_at",
]
STAGE_ORDER = ["expression", "understanding", "evaluation", "refinement"]
STAGE_LABELS = {
    "expression": "Expression – can't put memory into words",
    "understanding": "Understanding – search misreads the clues",
    "evaluation": "Evaluation – can't spot it among results",
    "refinement": "Refinement – can't adjust a failed search",
}
SEED_CSV = Path(__file__).parent / "data" / "insights_seed.csv"


# ---------- helpers ----------
def _secret(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:  # no secrets file at all
        return default


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[COLUMNS].dropna(how="all")
    df = df[df["url"].astype(str).str.strip() != ""]
    df = df.fillna("").astype(str)
    for c in ["photo_type", "intent", "failure_stage"]:
        df[c] = df[c].str.strip().str.lower()
    df["is_retrieval_problem"] = df["is_retrieval_problem"].str.upper().isin(["TRUE", "1", "YES"])
    return df.drop_duplicates(subset="url", keep="last")


def _read_public_sheet(sheet_url: str, tab: str = "insights") -> pd.DataFrame:
    """Reads one tab of a Google Sheet shared as 'Anyone with the link – Viewer'. No credentials needed."""
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", sheet_url)
    if not m:
        raise ValueError("INSIGHTS_SHEET_URL is not a Google Sheets URL")
    csv_url = (f"https://docs.google.com/spreadsheets/d/{m.group(1)}/gviz/tq"
               f"?tqx=out:csv&headers=1&sheet={quote(tab)}")
    r = requests.get(csv_url, timeout=20)
    r.raise_for_status()
    if "text/html" in r.headers.get("Content-Type", ""):
        raise PermissionError("Sheet is not shared as 'Anyone with the link can view'")
    return pd.read_csv(io.StringIO(r.text))


@st.cache_data(ttl=300, show_spinner="Loading community insights…")
def load_insights() -> tuple[pd.DataFrame, str]:
    """Returns (dataframe, where_it_came_from).
    Order: 1) link-shared sheet (INSIGHTS_SHEET_URL)  2) service account  3) local snapshot CSV."""
    public_url = _secret("INSIGHTS_SHEET_URL")
    if public_url:
        try:
            return _clean(_read_public_sheet(public_url)), "Live Google Sheet"
        except Exception:
            pass
    try:
        from streamlit_gsheets import GSheetsConnection

        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="insights", ttl=0)
        return _clean(df), "Live Google Sheet"
    except Exception:
        if SEED_CSV.exists():
            return _clean(pd.read_csv(SEED_CSV)), "Saved snapshot (data/insights_seed.csv)"
        return _clean(pd.DataFrame(columns=COLUMNS)), "No data source found"


THREAD_RE = re.compile(r"^https://support\.google\.com/photos/thread/\d+(?:/[^\s?#]*)?(?:\?[^\s#]*)?$")
POLL_TIMEOUT_S = 120
POLL_INTERVAL_S = 10


def _is_reddit_link(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    candidate = text if "://" in text else f"https://{text}"
    try:
        host = (urlparse(candidate).hostname or "").lower()
    except ValueError:
        return False
    return host == "reddit.com" or host.endswith(".reddit.com") or host == "redd.it" or host.endswith(".redd.it")


def _thread_id(url: str) -> str:
    match = re.search(r"/thread/(\d+)", url)
    if match is None:
        raise ValueError("Paste a Google Photos Community thread link.")
    return match.group(1)


def trigger_n8n(limit: int = 10, thread_url: str | None = None) -> str:
    """Starts the n8n workflow: a batch of pending threads, or one specific thread."""
    url = _secret("N8N_WEBHOOK_URL")
    if not url:
        raise RuntimeError("N8N_WEBHOOK_URL is missing from Streamlit secrets.")
    headers = {}
    key = _secret("N8N_WEBHOOK_KEY")
    if key:
        headers["X-Api-Key"] = key
    payload = {"limit": int(limit), "source": "streamlit"}
    if thread_url:
        thread_url = thread_url.strip()
        if not THREAD_RE.match(thread_url):
            raise ValueError("Paste a Google Photos Community thread link "
                             "(https://support.google.com/photos/thread/…).")
        payload = {"url": thread_url, "limit": 1, "source": "streamlit"}
    r = requests.post(url, json=payload, headers=headers, timeout=20)
    r.raise_for_status()
    return "started"


def _find_thread_row(df: pd.DataFrame, thread_id: str) -> pd.Series | None:
    if df.empty or "url" not in df.columns:
        return None
    hits = df[df["url"].astype(str).str.contains(f"/thread/{thread_id}", regex=False)]
    if hits.empty:
        return None
    return hits.iloc[-1]


def _poll_insights_row(sheet_url: str, thread_id: str, *, timeout_s: float = POLL_TIMEOUT_S,
                       interval_s: float = POLL_INTERVAL_S) -> pd.Series | None:
    """Read the public sheet directly, bypassing load_insights, until the thread appears."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            row = _find_thread_row(_clean(_read_public_sheet(sheet_url)), thread_id)
            if row is not None:
                return row
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(min(interval_s, max(0.0, deadline - time.monotonic())))


def _show_or_dash(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "—"


def _show_thread_card(row: pd.Series, *, already: bool) -> None:
    if already:
        st.info("Already analysed earlier. Here's the result.")
    stage = str(row.get("failure_stage") or "").strip().lower()
    stage_label = STAGE_LABELS.get(stage, stage.replace("_", " ") if stage else "—")
    about = "Yes" if bool(row.get("is_retrieval_problem")) else "No"
    quote = str(row.get("key_quote") or "").strip()
    url = str(row.get("url") or "").strip()
    with st.container(border=True):
        st.markdown(f"**{_show_or_dash(row.get('title'))}**")
        st.markdown(f"**About finding a photo:** {about}")
        st.markdown(f"**Photo type:** {_show_or_dash(row.get('photo_type')).replace('_', ' ')}")
        st.markdown(f"**Intent:** {_show_or_dash(row.get('intent')).replace('_', ' ')}")
        st.markdown(f"**Failure stage:** {stage_label}")
        st.markdown(f"**Cues remembered:** {_show_or_dash(row.get('cues_remembered'))}")
        st.markdown(f"**Cues forgotten:** {_show_or_dash(row.get('cues_forgotten'))}")
        st.markdown(f"**Query tried:** {_show_or_dash(row.get('query_tried'))}")
        if quote:
            quoted = "\n".join(f"> {line}" for line in quote.splitlines())
            st.markdown(quoted)
        if url:
            st.link_button("Open thread", url)


def _analyse_thread(thread_url: str) -> None:
    text = thread_url.strip()
    if _is_reddit_link(text):
        st.error("Reddit isn't supported (its API no longer issues keys).")
        return
    if not THREAD_RE.match(text):
        st.error("Paste a Google Photos Community thread link.")
        return
    thread_id = _thread_id(text)
    sheet_url = _secret("INSIGHTS_SHEET_URL")
    prior = None
    if sheet_url:
        try:
            prior = _find_thread_row(_clean(_read_public_sheet(sheet_url)), thread_id)
        except Exception:
            prior = None
    try:
        trigger_n8n(thread_url=text)
    except Exception:
        st.error("Could not start the analysis. Check the webhook settings.")
        return
    with st.status("Fetching thread → extracting the original post → tagging with AI…", expanded=True) as status:
        if prior is not None:
            row = prior
        elif sheet_url:
            row = _poll_insights_row(sheet_url, thread_id)
        else:
            row = None
        status.update(state="complete", expanded=row is not None)
    if row is None:
        st.info("Still processing. Click Refresh data in a minute.")
        return
    _show_thread_card(row, already=prior is not None)
    load_insights.clear()


def _top_items(series: pd.Series, n: int = 10) -> pd.DataFrame:
    s = (series.str.split(";").explode().str.strip().str.lower())
    s = s[(s != "") & (s != "unknown")]
    return s.value_counts().head(n).rename_axis("cue").reset_index(name="threads")


# ---------- UI ----------
def render_live_analyse() -> None:
    """Always-visible one-thread box from the Photo Discovery Lab overview."""
    with st.container(border=True):
        st.markdown("**Try it live: analyse a thread**")
        st.caption(
            "Paste one Google Photos Community link. The workflow fetches the original post, "
            "then tags it. A row already in the sheet is shown immediately."
        )
        thread_url = st.text_input(
            "Thread link",
            placeholder="https://support.google.com/photos/thread/…",
            label_visibility="collapsed",
            key="analyse_thread_url",
        )
        if st.button(":material/bolt: Analyse", type="primary", key="analyse_thread"):
            _analyse_thread(thread_url)
    st.caption(
        "The pipeline also runs daily: it reads the community's latest threads, "
        "keeps likely photo-finding ones, and tags them with AI."
    )


def render_community_insights() -> None:
    st.subheader("Google Photos Community – retrieval problems")
    render_live_analyse()

    with st.expander("Process queued threads"):
        c1, c2, c3 = st.columns([1, 1, 1])
        limit = c1.number_input("Threads per run", 1, 50, 10)
        if c2.button("▶ Fetch & tag new threads", width="stretch"):
            try:
                trigger_n8n(limit)
                st.success("Workflow started. Roughly 30 seconds per thread (Groq free-tier pacing) – "
                           "click **Refresh data** in a few minutes.")
            except Exception as e:
                st.error(f"Could not start the workflow: {e}")
        if c3.button("🔄 Refresh data", width="stretch"):
            load_insights.clear()
            st.rerun()

    df, origin = load_insights()
    st.caption(f"Data source: {origin}")
    if df.empty:
        st.info("No tagged threads yet. Add URLs to the `thread_urls` tab and run the workflow.")
        return

    rel = df[df["is_retrieval_problem"]]
    total, n_rel = len(df), len(rel)

    # KPI row
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Threads analysed", total)
    k2.metric("About finding a photo", n_rel, f"{n_rel / total:.0%} of threads", delta_color="off")
    staged = rel[rel["failure_stage"].isin(STAGE_ORDER)]
    if not staged.empty:
        top_stage = staged["failure_stage"].value_counts().idxmax()
        k3.metric("Top failure stage", top_stage.title(),
                  f"{(staged['failure_stage'] == top_stage).mean():.0%} of tagged", delta_color="off")
    pt = rel.loc[~rel["photo_type"].isin(["", "unknown"]), "photo_type"]
    if not pt.empty:
        k4.metric("Most-sought photo type", pt.value_counts().idxmax().replace("_", " / "))

    if rel.empty:
        st.warning("None of the analysed threads are retrieval problems yet – add more targeted URLs.")
        return

    # Filters
    f1, f2, f3 = st.columns(3)
    stages = f1.multiselect("Failure stage", STAGE_ORDER, default=STAGE_ORDER,
                            format_func=lambda s: s.title())
    types = f2.multiselect("Photo type", sorted(rel["photo_type"].unique()))
    intents = f3.multiselect("Intent", sorted(rel["intent"].unique()))
    view = rel[rel["failure_stage"].isin(stages)]
    if types:
        view = view[view["photo_type"].isin(types)]
    if intents:
        view = view[view["intent"].isin(intents)]

    # Where retrieval breaks
    st.markdown("#### Where retrieval breaks")
    stage_counts = (view["failure_stage"].value_counts()
                    .reindex(STAGE_ORDER, fill_value=0)
                    .rename(index=STAGE_LABELS))
    st.bar_chart(stage_counts, horizontal=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### What photos people look for")
        st.bar_chart(view["photo_type"].value_counts(), horizontal=True)
    with c2:
        st.markdown("#### Why they need it")
        st.bar_chart(view["intent"].value_counts(), horizontal=True)

    st.markdown("#### Failure stage × photo type")
    st.dataframe(pd.crosstab(view["failure_stage"], view["photo_type"]), width="stretch")

    # Memory cues
    st.markdown("#### What people remember vs. what they've forgotten")
    m1, m2 = st.columns(2)
    m1.caption("Remembered")
    m1.dataframe(_top_items(view["cues_remembered"]), hide_index=True, width="stretch")
    m2.caption("Forgotten")
    m2.dataframe(_top_items(view["cues_forgotten"]), hide_index=True, width="stretch")

    # Voices
    st.markdown("#### In their words")
    for _, r in view[view["key_quote"].str.len() > 0].head(8).iterrows():
        st.markdown(f"> {r['key_quote']}  \n"
                    f"<small>{r['photo_type']} · {r['failure_stage']} · [thread]({r['url']})</small>",
                    unsafe_allow_html=True)

    # Raw table + export
    st.markdown("#### All tagged threads")
    st.dataframe(
        view[["title", "photo_type", "intent", "failure_stage", "query_tried",
              "workaround", "summary", "url"]],
        hide_index=True, width="stretch",
        column_config={"url": st.column_config.LinkColumn("Thread", display_text="open")},
    )
    st.download_button("⬇ Download CSV", view.to_csv(index=False).encode(),
                       "community_insights.csv", "text/csv")


if __name__ == "__main__":  # lets you run this file on its own: streamlit run community_insights.py
    st.set_page_config(page_title="Community insights", layout="wide")
    render_community_insights()
