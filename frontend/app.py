"""
frontend/app.py
---------------
Streamlit UI for the CivicSight Civic Action Agent.
"""
import streamlit as st
import requests
import json

# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CivicSight — Report a Civic Issue",
    page_icon="🏛️",
    layout="centered",
)

# ---------------------------------------------------------------------------
# Custom CSS — premium dark theme
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background: #0d1117;
        color: #e6edf3;
    }
    .stApp { background: linear-gradient(135deg, #0d1117 0%, #161b22 100%); }

    h1 { color: #58a6ff; letter-spacing: -0.5px; }
    h3 { color: #8b949e; }

    .card {
        background: rgba(22,27,34,0.9);
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1.5rem 2rem;
        margin: 1rem 0;
        box-shadow: 0 4px 24px rgba(0,0,0,0.4);
    }
    .tracking-badge {
        display: inline-block;
        background: linear-gradient(90deg, #1f6feb, #388bfd);
        color: #fff;
        font-weight: 700;
        font-size: 1.3rem;
        padding: 0.4rem 1.2rem;
        border-radius: 8px;
        letter-spacing: 2px;
        margin: 0.5rem 0;
    }
    .severity-high   { color: #f85149; font-weight: 600; }
    .severity-medium { color: #d29922; font-weight: 600; }
    .severity-low    { color: #3fb950; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("# 🏛️ CivicSight")
st.markdown("### AI-Powered Civic Issue Reporting")
st.markdown("---")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_BASE = st.sidebar.text_input(
    "Backend URL", value="https://civic-sight-agent.vercel.app", help="FastAPI server address"
)

# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "history" not in st.session_state:
    st.session_state.history = []

# ---------------------------------------------------------------------------
# Input Form
# ---------------------------------------------------------------------------
with st.form("report_form", clear_on_submit=True):
    st.markdown("#### Describe the Civic Issue")
    message = st.text_area(
        "Issue Description",
        placeholder=(
            "e.g. 'There is a large pothole on MG Road near the City Mall entrance "
            "causing accidents. It has been there for 2 weeks.'"
        ),
        height=120,
    )
    image_url = st.text_input(
        "Image URL (optional)",
        placeholder="https://example.com/pothole.jpg",
    )
    submitted = st.form_submit_button("🚀 Submit Report", use_container_width=True)

# ---------------------------------------------------------------------------
# Handle Submission
# ---------------------------------------------------------------------------
if submitted and message.strip():
    with st.spinner("🤖 Analysing issue and registering with the Government portal..."):
        try:
            payload = {
                "message": message,
                "image_url": image_url.strip() or None,
                "session_id": st.session_state.session_id,
            }
            resp = requests.post(f"{API_BASE}/chat", json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            st.session_state.session_id = data.get("session_id")
            st.session_state.history.append(
                {
                    "message": message,
                    "tracking_id": data.get("tracking_id"),
                    "reply": data.get("reply", ""),
                }
            )

        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot reach the backend. Make sure the FastAPI server is running.")
        except Exception as exc:
            st.error(f"❌ Error: {exc}")
            if hasattr(exc, "response") and exc.response is not None:
                st.error(f"Backend details: {exc.response.text}")

elif submitted:
    st.warning("⚠️ Please describe the issue before submitting.")

# ---------------------------------------------------------------------------
# Display Results
# ---------------------------------------------------------------------------
if st.session_state.history:
    st.markdown("---")
    st.markdown("## 📋 Submission Results")

    for entry in reversed(st.session_state.history):
        with st.container():
            st.markdown(f"**Your report:** {entry['message']}")

            if entry.get("tracking_id"):
                st.markdown(
                    f"<div class='tracking-badge'>{entry['tracking_id']}</div>",
                    unsafe_allow_html=True,
                )

            if entry.get("reply"):
                st.markdown(
                    f"<div class='card'>{entry['reply']}</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("---")

# ---------------------------------------------------------------------------
# Sidebar Info
# ---------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.info(
    "**CivicSight** uses Google Gemini 2.0 Flash + ADK to "
    "automatically analyse civic issues and register them with "
    "the Government portal."
)
st.sidebar.markdown("**Pipeline:**")
st.sidebar.markdown("1. 🔍 Issue Analyser (Gemini)")
st.sidebar.markdown("2. 📝 Report Registrar (Tool call)")

if st.session_state.session_id:
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Session ID:** `{st.session_state.session_id[:8]}...`")
