import json
import os
from typing import Any, Dict, List

import env_utils
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://app:5001")
DEFAULT_DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

st.set_page_config(page_title="NoticeHub Dashboard", layout="wide")
st.title("NoticeHub Dashboard")

demo_mode = st.sidebar.checkbox("Demo mode", value=DEFAULT_DEMO_MODE)
demo_data = {}
if demo_mode:
    demo_path = os.path.join(os.path.dirname(__file__), "demo_data.json")
    try:
        with open(demo_path) as f:
            demo_data = json.load(f)
    except Exception as e:
        st.warning(f"Failed to load demo data: {e}")


def fetch_json(endpoint: str) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(f"{API_BASE}{endpoint}")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load {endpoint}: {e}")
        return []


def create_item(endpoint: str, payload: Dict[str, Any]):
    try:
        resp = requests.post(f"{API_BASE}{endpoint}", json=payload)
        resp.raise_for_status()
        st.success("Created successfully")
    except Exception as e:
        st.error(f"Creation failed: {e}")


page = st.sidebar.radio(
    "Navigation",
    ["Notifications", "Services", "Email Settings"],
)

if page == "Notifications":
    st.subheader("Notifications")
    if demo_mode:
        st.dataframe(demo_data.get("notifications", []))
    else:
        data = fetch_json("/api/v1/notifications")
        st.dataframe(data)

elif page == "Services":
    st.subheader("External Services")
    services = (
        demo_data.get("external_services", [])
        if demo_mode
        else fetch_json("/external-services")
    )
    st.dataframe(services)
    with st.expander("Add External Service"):
        with st.form("create_service"):
            s_name = st.text_input("Service name")
            s_provider = st.text_input("Provider")
            s_desc = st.text_area("Description")
            if st.form_submit_button("Create"):
                if demo_mode:
                    st.info("Demo mode: item not created.")
                else:
                    create_item(
                        "/external-services",
                        {
                            "service_name": s_name,
                            "provider": s_provider,
                            "description": s_desc,
                        },
                    )
                    services = fetch_json("/external-services")
                    st.experimental_rerun()

    st.subheader("Internal Systems")
    systems = (
        demo_data.get("internal_systems", [])
        if demo_mode
        else fetch_json("/internal-systems")
    )
    st.dataframe(systems)
    with st.expander("Add Internal System"):
        with st.form("create_system"):
            i_name = st.text_input("System name")
            i_contact = st.text_input("Responsible contact")
            i_desc = st.text_area("Description")
            if st.form_submit_button("Create"):
                if demo_mode:
                    st.info("Demo mode: item not created.")
                else:
                    create_item(
                        "/internal-systems",
                        {
                            "system_name": i_name,
                            "responsible_contact": i_contact,
                            "description": i_desc,
                        },
                    )
                    systems = fetch_json("/internal-systems")
                    st.experimental_rerun()

    deps = (
        demo_data.get("dependencies", []) if demo_mode else fetch_json("/dependencies")
    )
    st.subheader("Dependencies")
    dep_rows = [
        {
            "id": d.get("id"),
            "internal_system": d.get("internal_system", {}).get("system_name"),
            "external_service": d.get("external_service", {}).get("service_name"),
            "description": d.get("dependency_description"),
        }
        for d in deps
    ]
    st.dataframe(dep_rows)
    with st.expander("Add Dependency"):
        with st.form("create_dep"):
            internal = {s["system_name"]: s["id"] for s in systems}
            external = {s["service_name"]: s["id"] for s in services}
            dep_is = st.selectbox("Internal system", list(internal.keys()))
            dep_es = st.selectbox("External service", list(external.keys()))
            dep_desc = st.text_area("Description")
            if st.form_submit_button("Create"):
                if demo_mode:
                    st.info("Demo mode: item not created.")
                else:
                    create_item(
                        "/dependencies",
                        {
                            "internal_system_id": internal[dep_is],
                            "external_service_id": external[dep_es],
                            "dependency_description": dep_desc,
                        },
                    )
                    st.experimental_rerun()

    if services and systems and deps:
        import graphviz

        dot = "digraph Dependencies {" + "\n"
        for s in systems:
            dot += f'"{s["system_name"]}" [shape=box];\n'
        for s in services:
            dot += f'"{s["service_name"]}" [shape=ellipse];\n'
        for d in deps:
            isys = d.get("internal_system", {}).get("system_name")
            esvc = d.get("external_service", {}).get("service_name")
            if isys and esvc:
                dot += f'"{isys}" -> "{esvc}";\n'
        dot += "}"
        st.graphviz_chart(dot)

elif page == "Email Settings":
    st.subheader("Email Server Configuration")
    cfg = (
        demo_data.get("email_config", env_utils.load_env())
        if demo_mode
        else env_utils.load_env()
    )
    with st.form("email_cfg"):
        server = st.text_input("Server", cfg.get("EMAIL_SERVER", ""))
        port = st.number_input("Port", value=int(cfg.get("EMAIL_PORT", 993)), step=1)
        username = st.text_input("Username", cfg.get("EMAIL_USERNAME", ""))
        password = st.text_input(
            "Password", cfg.get("EMAIL_PASSWORD", ""), type="password"
        )
        folder = st.text_input("Folder", cfg.get("EMAIL_FOLDER", "INBOX"))
        interval = st.number_input(
            "Check interval (seconds)",
            value=int(cfg.get("EMAIL_CHECK_INTERVAL_SECONDS", 60)),
            step=1,
        )
        submitted = st.form_submit_button("Save")
    if submitted:
        if demo_mode:
            st.info("Demo mode: configuration not saved.")
        else:
            env_utils.update_env(
                {
                    "EMAIL_SERVER": server,
                    "EMAIL_PORT": int(port),
                    "EMAIL_USERNAME": username,
                    "EMAIL_PASSWORD": password,
                    "EMAIL_FOLDER": folder,
                    "EMAIL_CHECK_INTERVAL_SECONDS": int(interval),
                }
            )
            st.success("Configuration saved. Restart backend to apply changes.")
