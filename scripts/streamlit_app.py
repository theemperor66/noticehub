import os
from typing import Any, Dict, List

import env_utils
import pandas as pd
import requests
import streamlit as st
import streamlit_shadcn_ui as ui
import plotly.express as px
import plotly.graph_objects as go

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
    ["Dashboard", "Notifications", "Services", "Downtime", "Email Settings"],
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

    with st.expander("Create Notification from Sample Email"):
        demo_dir = os.path.join(os.path.dirname(__file__), "demo_emails")
        try:
            files = [f for f in os.listdir(demo_dir) if f.endswith(".html")]
        except Exception:
            files = []
        if files:
            selected = st.selectbox("Select sample email", files, key="demo_email")
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
                    "sender": "noreply@provider.com",
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
            st.info("No sample email files found.")

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

elif page == "Downtime":
    st.header("Service Downtime Statistics")
    
    # Fetch downtime statistics
    stats = fetch_json("/downtime-stats")
    
    if stats and len(stats) > 0:
        df_stats = pd.DataFrame(stats)
        
        # Fix field name inconsistencies - normalize column names
        if 'avg_downtime_minutes' in df_stats.columns and 'average_minutes' not in df_stats.columns:
            df_stats['average_minutes'] = df_stats['avg_downtime_minutes']
        
        # Check for ongoing events
        has_ongoing_events = df_stats['has_ongoing'].any() if 'has_ongoing' in df_stats.columns else False
        total_ongoing = df_stats['ongoing_count'].sum() if 'ongoing_count' in df_stats.columns else 0
        
        # Alert for ongoing issues if any exist
        if has_ongoing_events:
            st.warning(f"⚠️ There are currently {total_ongoing} ongoing service issue(s)")
        
        # Summary metrics in columns
        col1, col2, col3 = st.columns(3)
        
        # Determine which column to use for average downtime
        avg_col = 'average_minutes' if 'average_minutes' in df_stats.columns else 'avg_downtime_minutes'
        
        with col1:
            if not df_stats.empty and avg_col in df_stats.columns:
                avg_downtime = df_stats[avg_col].mean()
                # Format nicely with 1 decimal place
                st.metric("Average Downtime", f"{avg_downtime:.1f} min")
            else:
                st.metric("Average Downtime", "No data")
                
        with col2:
            if not df_stats.empty and 'event_count' in df_stats.columns:
                total_events = df_stats['event_count'].sum()
                st.metric("Total Downtime Events", f"{int(total_events)}")
            else:
                st.metric("Total Downtime Events", "No data")
                
        with col3:
            if not df_stats.empty and 'service_name' in df_stats.columns and avg_col in df_stats.columns:
                # Check if there are ongoing issues to consider
                if 'has_ongoing' in df_stats.columns and df_stats['has_ongoing'].any():
                    # First priority: services with ongoing issues
                    # If multiple services have ongoing issues, pick the one with highest average downtime
                    ongoing_services = df_stats[df_stats['has_ongoing'] == True]
                    if not ongoing_services.empty:
                        most_affected = ongoing_services.loc[ongoing_services[avg_col].idxmax()]['service_name']
                        # Add a visual indicator that this service has ongoing issues
                        st.metric("Most Affected Service", f"⚠️ {most_affected} (ongoing)")
                    else:
                        # Fallback to highest average if has_ongoing exists but no services are marked
                        most_affected = df_stats.loc[df_stats[avg_col].idxmax()]['service_name']
                        st.metric("Most Affected Service", most_affected)
                else:
                    # If no ongoing data available, use the original logic based on average downtime
                    most_affected = df_stats.loc[df_stats[avg_col].idxmax()]['service_name']
                    st.metric("Most Affected Service", most_affected)
            else:
                st.metric("Most Affected Service", "No data")
        
        # Ongoing events section (if any)
        if has_ongoing_events:
            st.subheader("Ongoing Service Issues")
            ongoing_df = df_stats[df_stats['has_ongoing'] == True].copy() if 'has_ongoing' in df_stats.columns else pd.DataFrame()
            if not ongoing_df.empty:
                # Create a table showing ongoing events
                ongoing_table = ongoing_df[['service_name', 'ongoing_count']].rename(
                    columns={
                        'service_name': 'Service', 
                        'ongoing_count': 'Ongoing Issues'
                    }
                )
                st.dataframe(ongoing_table, use_container_width=True, hide_index=True)
                
                # Highlight ongoing issues in red
                for service in ongoing_df['service_name'].tolist():
                    st.markdown(f"<span style='color:red'>⚠️ {service} has ongoing issues</span>", unsafe_allow_html=True)
        
        # Visualization section
        if not df_stats.empty and 'service_name' in df_stats.columns:
            # Determine the column to use for average downtime
            avg_col = 'average_minutes' if 'average_minutes' in df_stats.columns else 'avg_downtime_minutes'
            
            # Sort data by average downtime for better visualization
            df_stats = df_stats.sort_values(by=avg_col, ascending=False)
            
            # Create a bar chart of average downtime by service
            st.subheader("Average Downtime by Service")
            
            # Add color for services with ongoing issues
            if 'has_ongoing' in df_stats.columns:
                df_stats['Status'] = df_stats.apply(
                    lambda x: 'Ongoing Issues' if x['has_ongoing'] else 'Resolved', 
                    axis=1
                )
                color_discrete_map = {'Ongoing Issues': 'red', 'Resolved': 'blue'}
            else:
                df_stats['Status'] = 'Resolved'
                color_discrete_map = {'Resolved': 'blue'}
                
            # Add hover data if available
            hover_data = ['event_count']
            if 'ongoing_count' in df_stats.columns:
                hover_data.append('ongoing_count')
            
            # Use the appropriate column name for average downtime
            y_column = 'average_minutes' if 'average_minutes' in df_stats.columns else 'avg_downtime_minutes'
            
            fig = px.bar(
                df_stats, 
                x='service_name', 
                y=y_column, 
                color='Status',
                color_discrete_map=color_discrete_map,
                labels={'service_name': 'Service', y_column: 'Average Downtime (min)'},
                title='',
                hover_data=hover_data,
                height=400
            )
            fig.update_layout(
                xaxis_title="Service",
                yaxis_title="Average Downtime (minutes)",
                legend_title="Status"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Event count visualization
            st.subheader("Downtime Event Count by Service")
            
            # Create a better pie chart that shows actual proportions
            # Create direct proportional visualization using raw count values and go.Pie
            # This is more explicit than using px.pie and gives us full control
            event_counts = df_stats['event_count'].astype(int).tolist()
            service_names = df_stats['service_name'].tolist()
            
            # Calculate percentages manually for verification
            total_count = sum(event_counts)
            percentages = [count/total_count*100 for count in event_counts] if total_count > 0 else [0] * len(event_counts)
            
            # Create custom hover text with all the details we want
            hover_texts = []
            for i, service in enumerate(service_names):
                if 'ongoing_count' in df_stats.columns:
                    hover_texts.append(f"<b>{service}</b><br>" + 
                                      f"Count: {event_counts[i]}<br>" + 
                                      f"Percentage: {percentages[i]:.1f}%<br>" +
                                      f"Ongoing: {df_stats['ongoing_count'].iloc[i]}<br>" +
                                      f"Avg Duration: {df_stats['average_minutes'].iloc[i]:.1f} min")
                else:
                    hover_texts.append(f"<b>{service}</b><br>" + 
                                      f"Count: {event_counts[i]}<br>" + 
                                      f"Percentage: {percentages[i]:.1f}%<br>" +
                                      f"Avg Duration: {df_stats['average_minutes'].iloc[i]:.1f} min")
            
            # Create pie chart with go.Pie for maximum control
            fig2 = go.Figure(data=[go.Pie(
                labels=service_names,
                values=event_counts, 
                hole=0.4,
                hovertext=hover_texts,
                hoverinfo='text',
                textinfo='value+percent+label',
                textposition='inside',
                texttemplate='%{percent:.1f}% (%{value})<br>%{label}'
            )])
            
            fig2.update_layout(
                title='',
                legend=dict(orientation='h', y=-0.2)
            )
            st.plotly_chart(fig2, use_container_width=True)
            
            # Comprehensive data table with statistics
            st.subheader("Downtime Statistics Summary")
            
            # Choose columns based on whether we have ongoing data
            # First determine the correct column name for average downtime
            avg_col = 'average_minutes' if 'average_minutes' in df_stats.columns else 'avg_downtime_minutes'
            
            if 'ongoing_count' in df_stats.columns:
                display_columns = ['service_name', avg_col, 'event_count', 'ongoing_count']
                rename_map = {
                    'service_name': 'Service', 
                    avg_col: 'Avg. Downtime (min)', 
                    'event_count': 'Total Events',
                    'ongoing_count': 'Ongoing Issues'
                }
            else:
                display_columns = ['service_name', avg_col, 'event_count']
                rename_map = {
                    'service_name': 'Service', 
                    avg_col: 'Avg. Downtime (min)', 
                    'event_count': 'Event Count'
                }
                
            st.dataframe(
                df_stats[display_columns].rename(columns=rename_map),
                use_container_width=True,
                hide_index=True
            )
    else:
        st.info("No downtime statistics available. This could be because there are no recorded downtime events or due to data migration issues.")
        
    # Add option to view raw data if needed, but hidden by default
    with st.expander("Advanced: View Raw Event Data", expanded=False):
        st.caption("This shows the raw downtime event data. Most users won't need this information.")
        events = fetch_json("/downtime-events")
        if events:
            st.dataframe(events, use_container_width=True, height=300)
        else:
            st.info("No raw event data available.")

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
