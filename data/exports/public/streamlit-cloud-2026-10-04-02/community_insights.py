from pathlib import Path
import json
import streamlit as st


def render_community_insights() -> None:
    st.subheader('Community collection integration')
    st.info('Collection runs through the bounded owner CLI. Public visitors cannot trigger n8n, collection, or model spending.')
    st.write('The collection-only workflow returns original post text and provenance. The engine validates and imports it as CollectedDocument records, then uses existing normalization, privacy, deduplication and bounded research stages.')
    st.caption('Historical sheet tags remain unreviewed annotations. They are not original source text, validated quotations or approved cases.')
    path = Path(__file__).parent / 'data/exports/public/integration-status.json'
    if path.exists():
        metadata = json.loads(path.read_text(encoding='utf-8'))
        for key in ('implementation', 'live_connection', 'source_access', 'replies', 'last_import_documents'):
            st.write(f"{key.replace('_',' ').capitalize()}: {metadata.get(key,'not recorded')}")
    else:
        st.caption('Bridge implemented locally; n8n Cloud deployment and source-page compatibility are not yet verified.')
