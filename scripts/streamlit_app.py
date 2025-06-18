import requests
import streamlit as st

API_BASE = "http://app:5001"

st.title("NoticeHub Dashboard")

resp = requests.get(f"{API_BASE}/api/v1/notifications")
if resp.ok:
    for item in resp.json():
        st.subheader(item.get("title", "No title"))
        st.write(item)
else:
    st.error("Failed to load data")
