import os
from typing import Any, Dict, List

import env_utils
import pandas as pd
import requests
import streamlit as st
import streamlit_shadcn_ui as ui

# Valid notification status values that match NotificationStatusEnum
VALID_NOTIFICATION_STATUSES = [
    "new",
    "triaged",
    "action_pending",
    "in_progress",
    "resolved",
    "archived",
    "error_processing",
    "pending_manual_review",
    "pending_validation"
]

# Valid severity levels that match SeverityEnum
VALID_SEVERITY_LEVELS = [
    "low", 
    "medium", 
    "high", 
    "critical", 
    "info", 
    "unknown"
]

API_BASE = os.getenv("API_BASE", "http://app:5001")

st.set_page_config(page_title="NoticeHub Dashboard", layout="wide")
st.title("NoticeHub Dashboard")

# Inject reusable styles for status cards
css = """
.status-card {
    padding: 1rem;
    border-radius: 5px;
    margin-bottom: 1rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
    height: 100px;
    min-height: 100px;
    width: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
}
.status-red { background-color: #FF5252; color: white; }
.status-yellow { background-color: #FFD740; color: black; }
.status-green { background-color: #69F0AE; color: black; }

.equal-cols {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(60px, 1fr));
    gap: 5px;
    width: 100%;
}

.card-container {
    padding: 5px;
}
"""
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def fetch_json(endpoint: str) -> List[Dict[str, Any]]:
    try:
        resp = requests.get(f"{API_BASE}{endpoint}")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load {endpoint}: {e}")
        return []


def fetch_dict(endpoint: str) -> Dict[str, Any]:
    try:
        resp = requests.get(f"{API_BASE}{endpoint}")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load {endpoint}: {e}")
        return {}


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
    st.subheader("External Providers Dashboard")
    notifs = fetch_json("/api/v1/notifications")

    services = fetch_json("/external-services")

    systems = fetch_json("/internal-systems")

    deps = fetch_json("/dependencies")

    status_classes = {
        "none": "status-green",  # green
        "low": "status-green",
        "medium": "status-yellow",  # yellow
        "high": "status-red",  # red
    }
    variant_map = {
        "none": "secondary",
        "low": "secondary",
        "medium": "outline",
        "high": "destructive",
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
        # Handle empty list safely
        open_related = [n for n in related if n.get("status") != "resolved"] if related else []
        if open_related:
            try:
                latest = sorted(
                    open_related, key=lambda x: x.get("created_at", ""), reverse=True
                )[0]
                sev = latest.get("llm_data", {}).get("severity", "low")
                status = latest.get("status", "new")
            except (IndexError, KeyError):
                sev = "none"
                status = "operational"
        else:
            sev = "none"
            status = "operational"
        svc_status.append({"service": name, "status": status, "severity": sev})
    # Display service status cards using Streamlit's column system
    # Calculate number of columns (aim for cards of around 150-200px width)
    window_width = 1200  # Approximate width of a typical window
    card_width = 180     # Target width for each card
    num_cols = min(len(svc_status), max(3, window_width // card_width))  # At least 3 columns
    
    # Create columns
    cols = st.columns(num_cols)
    
    # Add each card to the appropriate column (distributing evenly)
    for idx, info in enumerate(svc_status):
        col_idx = idx % num_cols
        cls = status_classes.get(info["severity"], "status-green")
        sev_text = f" ({info['severity']})" if info["severity"] != "none" else ""
        
        with cols[col_idx]:
            html = (
                f"<div class='status-card {cls}' style='margin-bottom:10px; height:100px;'>"
                f"<strong>{info['service']}</strong><br>{info['status'].title()}{sev_text}"
                f"</div>"
            )
            st.markdown(html, unsafe_allow_html=True)
            
            # No badge display - removed as requested

    # Determine status for each internal system based on dependent services
    severity_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    svc_map = {s["service"]: s for s in svc_status}
    sys_status = []
    for sys in systems:
        name = sys.get("system_name")
        deps_for_sys = [
            d.get("external_service", {}).get("service_name")
            for d in deps
            if d.get("internal_system", {}).get("id") == sys.get("id")
        ]
        relevant = [svc_map[s] for s in deps_for_sys if s in svc_map]
        if relevant:
            sev = max(relevant, key=lambda x: severity_order.get(x["severity"], 0))[
                "severity"
            ]
            status = next(
                (r["status"] for r in relevant if r["severity"] == sev), "operational"
            )
        else:
            sev = "none"
            status = "operational"
        sys_status.append({"system": name, "status": status, "severity": sev})

    if sys_status:
        st.markdown("### Internal System Status")
        
        # Calculate number of columns (aim for cards of around 150-200px width)
        window_width = 1200  # Approximate width of a typical window
        card_width = 180     # Target width for each card
        num_cols = min(len(sys_status), max(3, window_width // card_width))  # At least 3 columns
        
        # Create columns
        cols = st.columns(num_cols)
        
        # Add each card to the appropriate column (distributing evenly)
        for idx, info in enumerate(sys_status):
            col_idx = idx % num_cols
            cls = status_classes.get(info["severity"], "status-green")
            sev_text = f" ({info['severity']})" if info["severity"] != "none" else ""
            
            with cols[col_idx]:
                html = (
                    f"<div class='status-card {cls}' style='margin-bottom:10px; height:100px;'>"
                    f"<strong>{info['system']}</strong><br>{info['status'].title()}{sev_text}"
                    f"</div>"
                )
                st.markdown(html, unsafe_allow_html=True)
                
                # No badge display - removed as requested

    # Add a bit of space before the table
    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    sys_map = {s["id"]: s["system_name"] for s in systems}
    # Get a list of all services for dropdowns
    all_services = [svc.get("service_name") for svc in services if svc.get("service_name")]
    
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
    if df.empty:
        df = pd.DataFrame(columns=["ID", "Service", "Notification", "Severity", "Status", "Impacted Systems"])
    
    # Add a dropdown for status field and other fields with valid values
    edited_df = st.data_editor(
        df,
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        key="impact_editor",
        height=300,
        column_config={
            "ID": st.column_config.NumberColumn(
                "ID",
                disabled=True,
                help="Auto-generated notification ID"
            ),
            "Service": st.column_config.SelectboxColumn(
                "Service", 
                options=all_services if all_services else ["No services available"],
                required=True
            ),
            "Notification": st.column_config.TextColumn(
                "Notification",
                required=True
            ),
            "Severity": st.column_config.SelectboxColumn(
                "Severity", 
                options=VALID_SEVERITY_LEVELS,
                required=True
            ),
            "Status": st.column_config.SelectboxColumn(
                "Status", 
                options=VALID_NOTIFICATION_STATUSES,
                required=True
            ),
            "Impacted Systems": st.column_config.TextColumn(
                "Impacted Systems",
                disabled=True,
                help="Automatically calculated based on service dependencies"
            )
        }
    )

    # Safe handling for empty dataframes and checking for deleted rows
    updated = False
    
    if not df.empty and "ID" in df.columns:
        # Only process deletions if we have IDs in both dataframes
        if "ID" in edited_df.columns:
            deleted_ids = set(df["ID"]) - set(edited_df["ID"])
            
            if deleted_ids:
                for d_id in deleted_ids:
                    try:
                        resp = requests.delete(f"{API_BASE}/api/v1/notifications/{d_id}")
                        resp.raise_for_status()
                    except Exception as e:
                        st.error(f"Failed to delete notification {d_id}: {e}")
                    else:
                        updated = True
    
        # Handle updates to existing rows
        if not df.empty and not edited_df.empty and "ID" in df.columns and "ID" in edited_df.columns:
            # Check if IDs match (no rows deleted or added)
            if set(df["ID"]) == set(edited_df["ID"]):
                for _, new_row in edited_df.iterrows():
                    if new_row["ID"] is not None and not pd.isna(new_row["ID"]):
                        orig_row_df = df[df["ID"] == new_row["ID"]]
                        if not orig_row_df.empty:
                            orig_row = orig_row_df.iloc[0]
                            payload = {}
                            if new_row["Notification"] != orig_row["Notification"]:
                                payload["title"] = new_row["Notification"]
                            if new_row["Severity"] != orig_row["Severity"]:
                                # Ensure severity is a valid enum value
                                if new_row["Severity"] in VALID_SEVERITY_LEVELS:
                                    payload["severity"] = new_row["Severity"]
                                else:
                                    st.warning(f"Invalid severity value: {new_row['Severity']}. Using original value.")
                                    payload["severity"] = orig_row["Severity"]
                            if new_row["Status"] != orig_row["Status"]:
                                # Ensure status is a valid enum value
                                if new_row["Status"] in VALID_NOTIFICATION_STATUSES:
                                    payload["status"] = new_row["Status"]
                                else:
                                    st.warning(f"Invalid status value: {new_row['Status']}. Using original value.")
                                    payload["status"] = orig_row["Status"]
                            if new_row["Service"] != orig_row["Service"]:
                                payload["service"] = new_row["Service"]
                            if payload:
                                try:
                                    resp = requests.put(
                                        f"{API_BASE}/api/v1/notifications/{new_row['ID']}",
                                        json=payload,
                                    )
                                    resp.raise_for_status()
                                except Exception as e:
                                    st.error(f"Failed to update notification {new_row['ID']}: {e}")
                                else:
                                    updated = True

    # Handle new rows (those with no ID or NaN ID)
    if not edited_df.empty and "ID" in edited_df.columns:
        # Look for rows where ID is NaN or None
        new_rows = edited_df[edited_df["ID"].isna()]
        for _, row in new_rows.iterrows():
            # Don't try to create notifications with empty data
            if pd.isna(row["Service"]) or pd.isna(row["Notification"]) or pd.isna(row["Status"]):
                continue
                
            payload = {
                "title": row["Notification"],
                "service": row["Service"],
                "severity": row["Severity"] if not pd.isna(row["Severity"]) else "info",
                "status": row["Status"] if not pd.isna(row["Status"]) else "new"
            }
            try:
                resp = requests.post(
                    f"{API_BASE}/api/v1/notifications",
                    json=payload
                )
                resp.raise_for_status()
            except Exception as e:
                st.error(f"Failed to create new notification: {e}")
            else:
                updated = True

    if updated:
        st.experimental_rerun()


elif page == "Notifications":
    st.subheader("Notifications")
    notifs = fetch_json("/api/v1/notifications")

    deps = fetch_json("/dependencies")

    systems = fetch_json("/internal-systems")
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
    st.dataframe(rows, use_container_width=True, height=400)

    with st.expander("Add Notification from Demo Email"):
        demo_dir = os.path.join(os.path.dirname(__file__), "demo_emails")
        try:
            files = [f for f in os.listdir(demo_dir) if f.endswith(".html")]
        except Exception:
            files = []
        if files:
            selected = st.selectbox("Select demo email", files, key="demo_email")
            email_path = os.path.join(demo_dir, selected)
            html_preview = ""
            try:
                with open(email_path) as f:
                    html_preview = f.read()
            except Exception as e:
                st.error(f"Failed to load {selected}: {e}")

            if html_preview:
                st.markdown("**Preview:**")
                st.components.v1.html(html_preview, height=200, scrolling=True)

            if st.button("Process Email"):
                subject = selected.replace("_", " ").replace(".html", "").title()
                payload = {
                    "subject": subject,
                    "html": html_preview,
                    "sender": "demo@provider.com",
                }
                resp = requests.post(
                    f"{API_BASE}/api/v1/process-html-email", json=payload
                )
                if resp.status_code == 201:
                    st.success("Email processed and notification created.")
                    st.experimental_rerun()
                else:
                    st.error(f"Failed to process email: {resp.text}")
        else:
            st.info("No demo email files found.")

elif page == "Services":
    st.subheader("External Services")
    services = fetch_json("/external-services")
    st.dataframe(services, use_container_width=True, height=400)
    with st.expander("Add External Service"):
        with st.form("create_service"):
            s_name = st.text_input("Service name")
            s_provider = st.text_input("Provider")
            s_desc = st.text_area("Description")
            if st.form_submit_button("Create"):
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
    systems = fetch_json("/internal-systems")
    st.dataframe(systems, use_container_width=True, height=400)
    with st.expander("Add Internal System"):
        with st.form("create_system"):
            i_name = st.text_input("System name")
            i_contact = st.text_input("Responsible contact")
            i_desc = st.text_area("Description")
            if st.form_submit_button("Create"):
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

    deps = fetch_json("/dependencies")
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
    st.dataframe(dep_rows, use_container_width=True, height=400)
    with st.expander("Add Dependency"):
        with st.form("create_dep"):
            internal = {s["system_name"]: s["id"] for s in systems}
            external = {s["service_name"]: s["id"] for s in services}
            dep_is = st.selectbox("Internal system", list(internal.keys()))
            dep_es = st.selectbox("External service", list(external.keys()))
            dep_desc = st.text_area("Description")
            if st.form_submit_button("Create"):
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
    cfg = fetch_dict("/api/v1/email-config")
    if not cfg:
        cfg = env_utils.load_env()
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
        payload = {
            "EMAIL_SERVER": server,
            "EMAIL_PORT": int(port),
            "EMAIL_USERNAME": username,
            "EMAIL_PASSWORD": password,
            "EMAIL_FOLDER": folder,
            "EMAIL_CHECK_INTERVAL_SECONDS": int(interval),
        }
        try:
            resp = requests.post(f"{API_BASE}/api/v1/email-config", json=payload)
            resp.raise_for_status()
            st.success("Configuration saved. Restart backend to apply changes.")
        except Exception as e:
            st.error(f"Failed to save configuration: {e}")
