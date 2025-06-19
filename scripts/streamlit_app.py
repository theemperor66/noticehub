import json
import os
from typing import Any, Dict, List

import pandas as pd

import env_utils
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://app:5001")
DEFAULT_DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

st.set_page_config(page_title="NoticeHub Dashboard", layout="wide")
st.title("NoticeHub Dashboard")

# Inject reusable styles for status cards
card_css = """
<style>
.status-card {padding:0.75rem;border-radius:4px;color:white;text-align:center;}
.status-green {background-color:#2ecc71;}
.status-yellow {background-color:#f1c40f;}
.status-red {background-color:#e74c3c;}
</style>
"""
st.markdown(card_css, unsafe_allow_html=True)

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
    ["Dashboard", "Notifications", "Services", "Email Settings"],
)

if page == "Dashboard":
    st.subheader("Service Impact Dashboard")
    if demo_mode:
        if "demo_notifications" not in st.session_state:
            st.session_state["demo_notifications"] = demo_data.get("notifications", [])
        notifs = st.session_state["demo_notifications"]
    else:
        notifs = fetch_json("/api/v1/notifications")
    services = (
        demo_data.get("external_services", [])
        if demo_mode
        else fetch_json("/external-services")
    )
    systems = (
        demo_data.get("internal_systems", [])
        if demo_mode
        else fetch_json("/internal-systems")
    )
    deps = (
        demo_data.get("dependencies", []) if demo_mode else fetch_json("/dependencies")
    )

    status_classes = {
        "none": "status-green",  # green
        "low": "status-green",
        "medium": "status-yellow",  # yellow
        "high": "status-red",  # red
    }

    # Determine current status for each service
    svc_status = []
    for svc in services:
        name = svc.get("service_name")
        related = [
            n
            for n in notifs
            if n.get("llm_data", {}).get("extracted_service_name") == name
        ]
        open_related = [n for n in related if n.get("status") != "resolved"]
        if open_related:
            latest = sorted(open_related, key=lambda x: x.get("created_at", ""), reverse=True)[0]
            sev = latest.get("llm_data", {}).get("severity", "low")
            status = latest.get("status", "new")
        else:
            sev = "none"
            status = "operational"
        svc_status.append({"service": name, "status": status, "severity": sev})
    # Display service status cards
    cols = st.columns(max(1, len(svc_status)))
    for idx, info in enumerate(svc_status):
        cls = status_classes.get(info["severity"], "status-green")
        sev_text = f" ({info['severity']})" if info["severity"] != "none" else ""
        html = (
            f"<div class='status-card {cls}'>"
            f"<strong>{info['service']}</strong><br>{info['status'].title()}{sev_text}</div>"
        )
        cols[idx % len(cols)].markdown(html, unsafe_allow_html=True)

    # Add a bit of space before the table
    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    sys_map = {s["id"]: s["system_name"] for s in systems}
    impact_rows = []
    for idx, n in enumerate(notifs):
        svc = n.get("llm_data", {}).get("extracted_service_name")
        impacted = [
            sys_map[d["internal_system"]["id"]]
            for d in deps
            if d.get("external_service", {}).get("service_name") == svc
        ]
        impact_rows.append(
            {
                "ID": n.get("id", idx),
                "Service": svc,
                "Notification": n.get("title"),
                "Severity": n.get("llm_data", {}).get("severity"),
                "Status": n.get("status"),
                "Impacted Systems": ", ".join(impacted) if impacted else "None",
            }
        )

    df = pd.DataFrame(impact_rows)
    edited_df = st.data_editor(
        df,
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        key="impact_editor",
    )

    deleted_ids = set(df["ID"]) - set(edited_df["ID"])
    if deleted_ids:
        if demo_mode:
            st.session_state["demo_notifications"] = [
                n for idx, n in enumerate(notifs) if n.get("id", idx) not in deleted_ids
            ]
        else:
            for d_id in deleted_ids:
                try:
                    requests.delete(f"{API_BASE}/api/v1/notifications/{d_id}")
                except Exception as e:
                    st.error(f"Failed to delete notification {d_id}: {e}")
        st.experimental_rerun()


elif page == "Notifications":
    st.subheader("Notifications")
    if demo_mode:
        if "demo_notifications" not in st.session_state:
            st.session_state["demo_notifications"] = demo_data.get("notifications", [])
        notifs = st.session_state["demo_notifications"]
    else:
        notifs = fetch_json("/api/v1/notifications")
    deps = (
        demo_data.get("dependencies", []) if demo_mode else fetch_json("/dependencies")
    )
    systems = (
        demo_data.get("internal_systems", [])
        if demo_mode
        else fetch_json("/internal-systems")
    )
    sys_map = {s["id"]: s["system_name"] for s in systems}
    rows = []
    for n in notifs:
        svc = n.get("llm_data", {}).get("extracted_service_name")
        impacted = [
            sys_map[d["internal_system"]["id"]]
            for d in deps
            if d.get("external_service", {}).get("service_name") == svc
        ]
        rows.append(
            {
                "title": n.get("title"),
                "service": svc,
                "severity": n.get("llm_data", {}).get("severity"),
                "status": n.get("status"),
                "impacted_systems": ", ".join(impacted) if impacted else "None",
                "created_at": n.get("created_at"),
            }
        )
    st.dataframe(rows)

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
