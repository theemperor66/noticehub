import json
import os
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://app:5001")
DEFAULT_DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

st.title("NoticeHub Dashboard")

# Sidebar toggle to switch demo mode on or off
demo_mode = st.sidebar.checkbox("Demo mode", value=DEFAULT_DEMO_MODE)

if demo_mode:
    st.sidebar.info("Demo mode enabled")
    demo_path = os.path.join(os.path.dirname(__file__), "demo_data.json")
    with open(demo_path) as f:
        demo_data = json.load(f)
    for item in demo_data:
        st.subheader(item.get("title", "No title"))
        st.write(item)
else:
    try:
        resp = requests.get(f"{API_BASE}/api/v1/notifications")
        resp.raise_for_status()
        for item in resp.json():
            st.subheader(item.get("title", "No title"))
            st.write(item)
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to load data: {e}")
