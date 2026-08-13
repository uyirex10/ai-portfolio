import html

import requests
import streamlit as st

# The UI talks to the API over HTTP only. It never imports rag_answer, so it
# holds no Qdrant lock and needs no API keys of its own.
API_URL = "http://localhost:8000/ask"
HEALTH_URL = "http://localhost:8000/health"
REQUEST_TIMEOUT = 240

st.set_page_config(page_title="Contract RAG", page_icon="closed_book", layout="centered")

STYLES = """
<style>
  .result-card { padding: 1rem 1.25rem; border-radius: 8px; border-left: 6px solid;
                 margin-bottom: 1rem; }
  .result-answer    { border-color: #2e7d32; background: rgba(46,125,50,0.10); }
  .result-content   { border-color: #ef6c00; background: rgba(239,108,0,0.10); }
  .result-threshold { border-color: #c62828; background: rgba(198,40,40,0.10); }
  .result-label { font-weight: 700; font-size: 0.78rem; letter-spacing: 0.08em;
                  text-transform: uppercase; margin-bottom: 0.5rem; }
  .result-body { font-size: 1rem; line-height: 1.55; white-space: pre-wrap; }
  .cite { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 0.85rem; padding: 0.15rem 0; }
</style>
"""
st.markdown(STYLES, unsafe_allow_html=True)

# One visual treatment per outcome, so which path fired is obvious at a glance.
OUTCOMES = {
    None: {
        "css": "result-answer",
        "label": "Answer",
        "note": "The model answered from the retrieved passages.",
    },
    "content": {
        "css": "result-content",
        "label": "Refused - answer not in the documents",
        "note": "Retrieval found relevant passages, but they do not contain the answer.",
    },
    "threshold": {
        "css": "result-threshold",
        "label": "Refused - nothing relevant retrieved",
        "note": "No passage was close enough to the question to be worth answering from.",
    },
}


def ask_api(question):
    """POST the question. Returns (payload, error_message); one is always None."""
    try:
        response = requests.post(API_URL, json={"question": question},
                                 timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ConnectionError:
        return None, (
            f"Cannot reach the API at {API_URL}.\n\n"
            "Start it with:\n\n"
            "    uvicorn api:app --host 127.0.0.1 --port 8000"
        )
    except requests.exceptions.Timeout:
        return None, (
            f"The API did not respond within {REQUEST_TIMEOUT} seconds. "
            "A cold start has to load the vector index, so the first request is slow."
        )
    except requests.exceptions.RequestException as exc:
        return None, f"Request to the API failed: {exc}"

    if response.status_code == 422:
        return None, "The API rejected that question as invalid. Please enter some text."
    if response.status_code != 200:
        return None, (f"The API returned HTTP {response.status_code}.\n\n"
                      f"{response.text[:400]}")

    try:
        return response.json(), None
    except ValueError:
        return None, "The API returned a response that was not valid JSON."


def render_result(payload):
    outcome = OUTCOMES.get(payload.get("refusal_type"), OUTCOMES[None])
    answer = (payload.get("answer") or "").strip()

    # Escaped: answers quote contract text, which contains & and < characters
    # that would otherwise break out of the card markup.
    st.markdown(
        f'<div class="result-card {outcome["css"]}">'
        f'<div class="result-label">{outcome["label"]}</div>'
        f'<div class="result-body">{html.escape(answer)}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(outcome["note"])

    citations = payload.get("citations") or []
    st.subheader(f"Citations ({len(citations)})")
    if not citations:
        st.write("No sources were cited.")
    else:
        for c in citations:
            st.markdown(
                f'<div class="cite">{html.escape(str(c["source_file"]))} '
            f'&mdash; page {c["page_number"]}</div>',
                unsafe_allow_html=True,
            )


st.title("Contract RAG")
st.write("Ask a question about the contract corpus.")

with st.form("ask"):
    question = st.text_input(
        "Question",
        placeholder="e.g. What is NCC's maximum total liability for loss of the Material?",
    )
    submitted = st.form_submit_button("Ask")

if submitted:
    if not question.strip():
        st.warning("Please enter a question first.")
    else:
        with st.spinner("Querying the API..."):
            payload, error = ask_api(question.strip())
        if error:
            st.error(error)
        else:
            render_result(payload)
