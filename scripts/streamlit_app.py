import requests
import streamlit as st

API_BASE = "http://app:5001"

st.title("NoticeHub Dashboard")

try:
    resp = requests.get(f"{API_BASE}/api/v1/notifications")
    resp.raise_for_status()
    for item in resp.json():
        st.subheader(item.get("title", "No title"))
        st.write(item)
except requests.exceptions.RequestException as e:
    st.error(f"Failed to load data: {e}")
