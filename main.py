import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.llm.base_llm import BaseLLM

from dateutil import parser as date_parser
from flask import Flask, g, jsonify, request
from sqlalchemy.orm import Session, joinedload

from src import config
from src.data import crud
from src.data.models import (
    Dependency,
    ExternalService,
    DowntimeEvent,
    InternalSystem,
    LLMData,
    Notification,
    NotificationStatusEnum,
    NotificationTypeEnum,
    ProcessingStatusEnum,
    RawEmail,
    SeverityEnum,
    create_tables,
    get_db_session,
)
from src.data.seed_demo_data import seed_demo_data
from src.data.schemas import (
    DependencyCreate,
    DependencyList,
    DependencySchema,
    DependencyUpdate,
    ExternalServiceCreate,
    ExternalServiceList,
    ExternalServiceSchema,
    ExternalServiceUpdate,
    DowntimeEventSchema,
    DowntimeStatsSchema,
    InternalSystemCreate,
    InternalSystemList,
    InternalSystemSchema,
    InternalSystemUpdate,
)
from src.email.client import EmailClient
from src.email.parser import clean_email_body, parse_html_to_text, pre_filter_email
from src.llm.llm_factory import LLMFactory
from src.notifications.notifier import send_email_notification
from src.utils.logger import logger

sys.path.append(os.path.join(os.path.dirname(__file__), "scripts"))
import env_utils

logger.info("Initializing NoticeHub...")

# --- Flask App Setup ---
app = Flask(__name__)

# --- Pre-filter Configuration (Placeholder - should be from config) ---
SENDER_WHITELIST = ["cloudprovider.com", "status.example.com", "alerts@service.com"]
SENDER_BLACKLIST = ["marketing@example.com", "spam@example.net"]
SUBJECT_KEYWORDS = [
    "Maintenance",
    "Outage",
    "Störung",
    "Wartung",
    "Incident",
    "Alert",
    "Update",
    "Degradation",
    "Resolved",
]

# --- LLM Prompt Definition
INITIAL_EXTRACTION_PROMPT_TEMPLATE = """
Extract the following information from the email content provided below.
Return the information as a JSON object with these exact keys:
'extracted_service_name', 'event_start_time', 'event_end_time', 'notification_type', 'event_summary', 'severity_level'.

- 'extracted_service_name': The name of the service mentioned (e.g., "AWS EC2", "GitHub Actions").
- 'extracted_service_name': Choose from the following known services when possible: {service_options}
- 'event_start_time': The start date and time of the event (YYYY-MM-DD HH:MM UTC or ISO 8601). If not found, use null.
- 'event_end_time': The end date and time of the event (YYYY-MM-DD HH:MM UTC or ISO 8601). If not found, use null.
- 'notification_type': One of ["maintenance", "outage", "update", "alert", "info", "security", "unknown"].
- 'event_summary': A brief summary of the event or notification (1-2 sentences).
- 'severity_level': One of ["low", "medium", "high", "critical", "info", "unknown"].

Always include every key. Use null when a value is missing. Provide only JSON with no extra text.

Email content:
---BEGIN EMAIL CONTENT---
Subject: {email_subject}
Body:
{email_body}
---END EMAIL CONTENT---

JSON Output:
"""


# --- Database Session Management for Flask ---
@app.before_request
def get_session():
    if "db" not in g:
        g.db = get_db_session()


@app.teardown_appcontext
def close_session(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --- Serialization Helpers ---
def serialize_datetime(dt_obj: Optional[datetime]) -> Optional[str]:
    return dt_obj.isoformat() if dt_obj else None


def serialize_enum(enum_obj: Optional[Any]) -> Optional[str]:
    return enum_obj.value if enum_obj else None


def serialize_raw_email(raw_email: Optional[RawEmail]) -> Optional[Dict[str, Any]]:
    if not raw_email:
        return None
    return {
        "id": raw_email.id,
        "original_email_id_hash": raw_email.original_email_id_hash,
        "subject": raw_email.subject,
        "sender": raw_email.sender,
        "received_at": serialize_datetime(raw_email.received_at),
        "has_html_body": raw_email.has_html_body,
        "created_at": serialize_datetime(raw_email.created_at),
        "updated_at": serialize_datetime(raw_email.updated_at),
    }


def serialize_llm_data(llm_data: Optional[LLMData]) -> Optional[Dict[str, Any]]:
    if not llm_data:
        return None
    return {
        "id": llm_data.id,
        "extracted_service_name": llm_data.extracted_service_name,
        "event_start_time": serialize_datetime(llm_data.event_start_time),
        "event_end_time": serialize_datetime(llm_data.event_end_time),
        "notification_type": serialize_enum(llm_data.notification_type),
        "severity": serialize_enum(llm_data.severity),
        "llm_summary": llm_data.llm_summary,
        "raw_llm_response": llm_data.raw_llm_response,  # Potentially large, consider omitting or truncating in list views
        "processing_status": serialize_enum(llm_data.processing_status),
        "error_message": llm_data.error_message,
        "created_at": serialize_datetime(llm_data.created_at),
        "updated_at": serialize_datetime(llm_data.updated_at),
    }


def serialize_notification(notification: Notification) -> Dict[str, Any]:
    return {
        "id": notification.id,
        "title": notification.title,
        "status": serialize_enum(notification.status),
        "created_at": serialize_datetime(notification.created_at),
        "updated_at": serialize_datetime(notification.updated_at),
        "last_checked_at": serialize_datetime(notification.last_checked_at),
        "raw_email_data": (
            serialize_raw_email(notification.raw_email_data)
            if notification.raw_email_data
            else None
        ),  # Eager load if needed often
        "llm_data": (
            serialize_llm_data(notification.llm_data) if notification.llm_data else None
        ),  # Eager load if needed often
        # Relationships (example, assuming they exist on Notification model)
        # "affected_services": [service.name for service in notification.affected_services],
        # "dependencies": [dep.name for dep in notification.dependencies],
        # "internal_systems": [sys.name for sys in notification.internal_systems]
    }


def serialize_downtime_event(event: DowntimeEvent) -> Dict[str, Any]:
    return {
        "id": event.id,
        "service_id": event.external_service_id,
        "service_name": event.external_service.service_name if event.external_service else None,
        "start_notification_id": event.start_notification_id,
        "end_notification_id": event.end_notification_id,
        "start_time": serialize_datetime(event.start_time),
        "end_time": serialize_datetime(event.end_time),
        "severity": serialize_enum(event.severity),
        "summary": event.summary,
        "duration_minutes": event.duration_minutes,
    }


# --- API Endpoints ---
@app.route("/api/v1/health", methods=["GET"])
def health_check():
    db: Session = g.db
    try:
        # Basic DB check
        db.execute("SELECT 1")
        return jsonify(status="ok", database="connected"), 200
    except Exception as e:
        logger.error(f"Health check DB error: {e}", exc_info=True)
        return jsonify(status="error", database="disconnected", error=str(e)), 500


@app.route("/api/v1/notifications", methods=["GET"])
def get_notifications_list():
    db: Session = g.db
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 100, type=int)
    notifications = crud.get_notifications(
        db,
        skip=skip,
        limit=limit,
        options=[
            joinedload(Notification.raw_email_data),
            joinedload(Notification.llm_data),
        ],
    )
    return jsonify([serialize_notification(n) for n in notifications])


@app.route("/api/v1/notifications/<int:notification_id>", methods=["GET"])
def get_notification_detail(notification_id: int):
    db: Session = g.db
    notification = crud.get_notification(
        db,
        notification_id=notification_id,
        options=[
            joinedload(Notification.raw_email_data),
            joinedload(Notification.llm_data),
        ],
    )
    if notification is None:
        return jsonify(error="Notification not found"), 404
    return jsonify(serialize_notification(notification))


@app.route("/api/v1/notifications/<int:notification_id>", methods=["PUT"])
def update_notification_endpoint(notification_id: int):
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    data = request.json or {}

    status_raw = data.get("status")
    severity_raw = data.get("severity")
    title = data.get("title")
    service = data.get("service") or data.get("service_name")

    status_enum = None
    severity_enum = None
    if status_raw is not None:
        try:
            status_enum = NotificationStatusEnum(status_raw)
        except ValueError:
            return jsonify({"error": f"Invalid status '{status_raw}'"}), 400
    if severity_raw is not None:
        try:
            severity_enum = SeverityEnum(severity_raw)
        except ValueError:
            return jsonify({"error": f"Invalid severity '{severity_raw}'"}), 400

    updated = crud.update_notification(
        g.db,
        notification_id,
        title=title,
        status=status_enum,
        service_name=service,
        severity=severity_enum,
    )
    if not updated:
        return (
            jsonify({"error": f"Notification with ID {notification_id} not found"}),
            404,
        )
    return jsonify(serialize_notification(updated))


@app.route("/api/v1/notifications/<int:notification_id>", methods=["DELETE"])
def delete_notification_api(notification_id: int):
    # First verify the notification exists before attempting to delete
    notification = None
    try:
        notification = g.db.query(Notification).filter(Notification.id == notification_id).first()
    except Exception as e:
        logger.error(f"Error querying notification {notification_id} before deletion: {e}", exc_info=True)
        return (
            jsonify({"error": f"Database error while checking notification {notification_id}", "details": str(e)}),
            500,
        )
        
    if not notification:
        # Log more info about the request context for debugging
        logger.warning(
            f"DELETE request for non-existent notification ID {notification_id}. "
            f"Request path: {request.path}, IP: {request.remote_addr}, "
            f"User-Agent: {request.headers.get('User-Agent')}"
        )
        return (
            jsonify({
                "error": f"Notification with ID {notification_id} not found",
                "details": "The notification may have been deleted already or never existed"
            }),
            404,
        )
    
    # Check whether this notification is the start of any downtime events.
    referenced_as_start = g.db.query(DowntimeEvent).filter(
        DowntimeEvent.start_notification_id == notification_id
    ).count()

    if referenced_as_start > 0:
        logger.info(
            f"Notification ID {notification_id} starts {referenced_as_start} downtime events. They will be deleted as well."
        )

    # Count how many events reference it as the end notification just for logging
    referenced_as_end = g.db.query(DowntimeEvent).filter(
        DowntimeEvent.end_notification_id == notification_id
    ).count()

    if referenced_as_end > 0:
        logger.info(
            f"Notification ID {notification_id} is referenced by {referenced_as_end} "
            "downtime events as end notification. Those events will be reopened."
        )
    
    # Attempt the deletion in CRUD. This will also delete any downtime events
    # started by this notification and reopen those that end with it.
    success = crud.delete_notification(g.db, notification_id)
    if not success:
        # This is unexpected since we verified existence and no references
        logger.error(f"Failed to delete notification {notification_id} for unknown reason")
        return (
            jsonify({
                "error": f"Failed to delete notification {notification_id}",
                "details": "See server logs for details"
            }),
            500,
        )
    
    return (
        jsonify({"message": f"Notification {notification_id} deleted successfully"}),
        200,
    )


# --- ExternalService API Endpoints ---


@app.route("/external-services", methods=["POST"])
def api_create_external_service():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    try:
        service_data = ExternalServiceCreate(**request.json)
    except Exception as e:  # Handles Pydantic validation errors
        logger.error(
            f"Error validating external service creation data: {e}", exc_info=True
        )
        # Pydantic v2 errors can be complex; str(e) gives a good summary.
        return (
            jsonify(
                {"error": "Invalid input for external service.", "details": str(e)}
            ),
            400,
        )

    db_service = crud.create_external_service(
        db=g.db,
        service_name=service_data.service_name,
        provider=service_data.provider,
        description=service_data.description,
    )
    # create_external_service already handles if it already exists and returns it
    # If we wanted to return 409 Conflict if it already exists and we didn't want to return the existing one:
    # if crud.get_external_service_by_name(db=g.db, service_name=service_data.service_name):
    #     return jsonify({"error": f"External service with name '{service_data.service_name}' already exists."}), 409
    return jsonify(ExternalServiceSchema.model_validate(db_service).model_dump()), 201


@app.route("/external-services", methods=["GET"])
def api_get_external_services():
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 100, type=int)
    services_models = crud.get_external_services(db=g.db, skip=skip, limit=limit)
    # For total_count, we'd ideally have a separate count function in crud or do it here.
    # For simplicity now, we'll just count the returned list if it's less than limit, or assume more if it hits limit.
    # A proper count would be: total_services = g.db.query(crud.ExternalService).count()
    total_count = len(
        services_models
    )  # This is not the *true* total if paginated and not on the last page.
    # A more accurate count would require another DB query.

    services_schemas = [
        ExternalServiceSchema.model_validate(s).model_dump() for s in services_models
    ]
    # To implement full list response with total_count:
    # response_data = ExternalServiceList(services=services_schemas, total_count=total_services_count_from_db).model_dump()
    # return jsonify(response_data)
    return jsonify(services_schemas)


@app.route("/external-services/<int:service_id>", methods=["GET"])
def api_get_external_service(service_id: int):
    db_service = crud.get_external_service(db=g.db, service_id=service_id)
    if db_service is None:
        return (
            jsonify({"error": f"External service with ID {service_id} not found"}),
            404,
        )
    return jsonify(ExternalServiceSchema.model_validate(db_service).model_dump())


@app.route("/external-services/<int:service_id>", methods=["PUT"])
def api_update_external_service(service_id: int):
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    try:
        update_data = ExternalServiceUpdate(**request.json)
    except Exception as e:
        logger.error(
            f"Error validating external service update data for ID {service_id}: {e}",
            exc_info=True,
        )
        return (
            jsonify(
                {
                    "error": "Invalid input for external service update.",
                    "details": str(e),
                }
            ),
            400,
        )

    # Filter out fields that were not provided in the request (Pydantic models default None)
    update_args = {k: v for k, v in update_data.model_dump().items() if v is not None}

    if not update_args:
        return (
            jsonify({"message": "No update data provided."}),
            200,
        )  # Or 400 if an update must contain data

    updated_service = crud.update_external_service(
        db=g.db, service_id=service_id, **update_args
    )

    if updated_service is None:
        # crud.update_external_service returns None if not found or if name conflict during update
        # A more specific error could be returned from crud or checked here
        # For now, assume 404 if None, or it could be a 409 if name conflict was the reason
        # Let's check if the service still exists to differentiate 404 from potential 409 (name conflict)
        if not crud.get_external_service(db=g.db, service_id=service_id):
            return (
                jsonify({"error": f"External service with ID {service_id} not found."}),
                404,
            )
        else:  # Service exists, so update failed for another reason (e.g. name conflict)
            return (
                jsonify(
                    {
                        "error": f"Failed to update external service ID {service_id}. Possible name conflict or other validation error."
                    }
                ),
                409,
            )

    return jsonify(ExternalServiceSchema.model_validate(updated_service).model_dump())


@app.route("/external-services/<int:service_id>", methods=["DELETE"])
def api_delete_external_service(service_id: int):
    # crud.delete_external_service returns False if not found or if it has dependencies
    success = crud.delete_external_service(db=g.db, service_id=service_id)
    if not success:
        # To differentiate: check if service exists. If not, it's a 404. If it exists, it had dependencies (409 Conflict).
        db_service = crud.get_external_service(db=g.db, service_id=service_id)
        if db_service is None:
            return (
                jsonify(
                    {
                        "error": f"External service with ID {service_id} not found for deletion."
                    }
                ),
                404,
            )
        else:
            # If it exists but deletion failed, it's because of dependencies
            return (
                jsonify(
                    {
                        "error": f"Cannot delete external service ID {service_id}. It may have active dependencies."
                    }
                ),
                409,
            )
    return (
        jsonify(
            {"message": f"External service with ID {service_id} deleted successfully."}
        ),
        200,
    )


# --- InternalSystem API Endpoints ---


@app.route("/internal-systems", methods=["POST"])
def api_create_internal_system():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    try:
        system_data = InternalSystemCreate(**request.json)
    except Exception as e:
        logger.error(
            f"Error validating internal system creation data: {e}", exc_info=True
        )
        return (
            jsonify({"error": "Invalid input for internal system.", "details": str(e)}),
            400,
        )

    db_system = crud.create_internal_system(
        db=g.db,
        system_name=system_data.system_name,
        responsible_contact=system_data.responsible_contact,
        description=system_data.description,
    )
    return jsonify(InternalSystemSchema.model_validate(db_system).model_dump()), 201


@app.route("/internal-systems", methods=["GET"])
def api_get_internal_systems():
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 100, type=int)
    systems_models = crud.get_internal_systems(db=g.db, skip=skip, limit=limit)
    systems_schemas = [
        InternalSystemSchema.model_validate(s).model_dump() for s in systems_models
    ]
    # For a full list response with total_count, similar to ExternalServiceList:
    # total_count = g.db.query(crud.InternalSystem).count() # Example for total count
    # response_data = InternalSystemList(systems=systems_schemas, total_count=total_count).model_dump()
    # return jsonify(response_data)
    return jsonify(systems_schemas)


@app.route("/internal-systems/<int:system_id>", methods=["GET"])
def api_get_internal_system(system_id: int):
    db_system = crud.get_internal_system(db=g.db, system_id=system_id)
    if db_system is None:
        return jsonify({"error": f"Internal system with ID {system_id} not found"}), 404
    return jsonify(InternalSystemSchema.model_validate(db_system).model_dump())


@app.route("/internal-systems/<int:system_id>", methods=["PUT"])
def api_update_internal_system(system_id: int):
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    try:
        update_data = InternalSystemUpdate(**request.json)
    except Exception as e:
        logger.error(
            f"Error validating internal system update data for ID {system_id}: {e}",
            exc_info=True,
        )
        return (
            jsonify(
                {
                    "error": "Invalid input for internal system update.",
                    "details": str(e),
                }
            ),
            400,
        )

    update_args = {k: v for k, v in update_data.model_dump().items() if v is not None}

    if not update_args:
        return jsonify({"message": "No update data provided."}), 200

    updated_system = crud.update_internal_system(
        db=g.db, system_id=system_id, **update_args
    )

    if updated_system is None:
        if not crud.get_internal_system(db=g.db, system_id=system_id):
            return (
                jsonify({"error": f"Internal system with ID {system_id} not found."}),
                404,
            )
        else:
            return (
                jsonify(
                    {
                        "error": f"Failed to update internal system ID {system_id}. Possible name conflict or other validation error."
                    }
                ),
                409,
            )

    return jsonify(InternalSystemSchema.model_validate(updated_system).model_dump())


@app.route("/internal-systems/<int:system_id>", methods=["DELETE"])
def api_delete_internal_system(system_id: int):
    success = crud.delete_internal_system(db=g.db, system_id=system_id)
    if not success:
        db_system = crud.get_internal_system(db=g.db, system_id=system_id)
        if db_system is None:
            return (
                jsonify(
                    {
                        "error": f"Internal system with ID {system_id} not found for deletion."
                    }
                ),
                404,
            )
        else:
            return (
                jsonify(
                    {
                        "error": f"Cannot delete internal system ID {system_id}. It may have active dependencies."
                    }
                ),
                409,
            )
    return (
        jsonify(
            {"message": f"Internal system with ID {system_id} deleted successfully."}
        ),
        200,
    )


# --- Dependency API Endpoints ---


@app.route("/dependencies", methods=["POST"])
def api_create_dependency():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    try:
        dep_data = DependencyCreate(**request.json)
    except Exception as e:
        logger.error(f"Error validating dependency creation data: {e}", exc_info=True)
        return (
            jsonify({"error": "Invalid input for dependency.", "details": str(e)}),
            400,
        )

    # Check if parent InternalSystem exists
    if not crud.get_internal_system(db=g.db, system_id=dep_data.internal_system_id):
        return (
            jsonify(
                {
                    "error": f"InternalSystem with ID {dep_data.internal_system_id} not found."
                }
            ),
            404,
        )

    # Check if parent ExternalService exists
    if not crud.get_external_service(db=g.db, service_id=dep_data.external_service_id):
        return (
            jsonify(
                {
                    "error": f"ExternalService with ID {dep_data.external_service_id} not found."
                }
            ),
            404,
        )

    db_dependency = crud.create_dependency(
        db=g.db,
        internal_system_id=dep_data.internal_system_id,
        external_service_id=dep_data.external_service_id,
        dependency_description=dep_data.dependency_description,
    )

    # crud.create_dependency returns the existing one if it's a duplicate.
    # If it returned None strictly for missing parents (which we check above now), this would be different.
    # Assuming 201 for new, and if it's existing, it's treated as a successful 'get or create'.
    return jsonify(DependencySchema.model_validate(db_dependency).model_dump()), 201


@app.route("/dependencies", methods=["GET"])
def api_get_dependencies():
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 100, type=int)

    # Optional filtering by internal_system_id or external_service_id
    internal_system_id = request.args.get("internal_system_id", type=int)
    external_service_id = request.args.get("external_service_id", type=int)

    if internal_system_id:
        dependencies_models = crud.get_dependencies_for_internal_system(
            db=g.db, internal_system_id=internal_system_id, skip=skip, limit=limit
        )
    elif external_service_id:
        dependencies_models = crud.get_dependencies_for_external_service(
            db=g.db, external_service_id=external_service_id, skip=skip, limit=limit
        )
    else:
        dependencies_models = crud.get_dependencies(db=g.db, skip=skip, limit=limit)

    dependencies_schemas = [
        DependencySchema.model_validate(d).model_dump() for d in dependencies_models
    ]
    # To implement full list response with total_count:
    # total_count = g.db.query(crud.Dependency).count() # This would need to adapt to filters too
    # response_data = DependencyList(dependencies=dependencies_schemas, total_count=total_count).model_dump()
    # return jsonify(response_data)
    return jsonify(dependencies_schemas)


@app.route("/dependencies/<int:dependency_id>", methods=["GET"])
def api_get_dependency(dependency_id: int):
    db_dependency = crud.get_dependency(db=g.db, dependency_id=dependency_id)
    if db_dependency is None:
        return jsonify({"error": f"Dependency with ID {dependency_id} not found"}), 404
    return jsonify(DependencySchema.model_validate(db_dependency).model_dump())


@app.route("/dependencies/<int:dependency_id>", methods=["PUT"])
def api_update_dependency(dependency_id: int):
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    try:
        update_data = DependencyUpdate(**request.json)
    except Exception as e:
        logger.error(
            f"Error validating dependency update data for ID {dependency_id}: {e}",
            exc_info=True,
        )
        return (
            jsonify(
                {"error": "Invalid input for dependency update.", "details": str(e)}
            ),
            400,
        )

    # update_dependency in CRUD currently only handles 'dependency_description'
    updated_dependency = crud.update_dependency(
        db=g.db,
        dependency_id=dependency_id,
        dependency_description=update_data.dependency_description,
    )

    if updated_dependency is None:
        # This implies the dependency ID itself was not found by crud.update_dependency
        return jsonify({"error": f"Dependency with ID {dependency_id} not found."}), 404

    return jsonify(DependencySchema.model_validate(updated_dependency).model_dump())


@app.route("/dependencies/<int:dependency_id>", methods=["DELETE"])
def api_delete_dependency(dependency_id: int):
    success = crud.delete_dependency(db=g.db, dependency_id=dependency_id)
    if not success:
        # crud.delete_dependency returns False if not found.
        return (
            jsonify(
                {
                    "error": f"Dependency with ID {dependency_id} not found or could not be deleted."
                }
            ),
            404,
        )
    return (
        jsonify(
            {"message": f"Dependency with ID {dependency_id} deleted successfully."}
        ),
        200,
    )


@app.route("/downtime-events", methods=["GET"])
def api_get_downtime_events():
    service_id = request.args.get("service_id", type=int)
    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 100, type=int)
    events = crud.get_downtime_events(
        g.db, external_service_id=service_id, skip=skip, limit=limit
    )
    return jsonify([serialize_downtime_event(e) for e in events])


@app.route("/downtime-stats", methods=["GET"])
def api_get_downtime_stats():
    stats = crud.get_average_downtime_by_service(g.db)
    return jsonify([DowntimeStatsSchema.model_validate(s).model_dump() for s in stats])


# --- Email Configuration API Endpoints ---


@app.route("/api/v1/email-config", methods=["GET"])
def api_get_email_config():
    """Return the currently loaded email configuration."""
    return jsonify(
        {
            "EMAIL_SERVER": config.settings.email_server,
            "EMAIL_PORT": config.settings.email_port,
            "EMAIL_USERNAME": config.settings.email_username,
            "EMAIL_PASSWORD": config.settings.email_password,
            "EMAIL_FOLDER": config.settings.email_folder,
            "EMAIL_CHECK_INTERVAL_SECONDS": config.settings.email_check_interval_seconds,
        }
    )


@app.route("/api/v1/email-config", methods=["POST"])
def api_update_email_config_endpoint():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    data = request.json or {}
    update_values = {
        "EMAIL_SERVER": data.get("EMAIL_SERVER"),
        "EMAIL_PORT": data.get("EMAIL_PORT"),
        "EMAIL_USERNAME": data.get("EMAIL_USERNAME"),
        "EMAIL_PASSWORD": data.get("EMAIL_PASSWORD"),
        "EMAIL_FOLDER": data.get("EMAIL_FOLDER"),
        "EMAIL_CHECK_INTERVAL_SECONDS": data.get("EMAIL_CHECK_INTERVAL_SECONDS"),
    }
    env_utils.update_env({k: v for k, v in update_values.items() if v is not None})
    return jsonify({"message": "Configuration updated"})


@app.route("/api/v1/process-html-email", methods=["POST"])
def api_process_html_email():
    """Create a notification from posted HTML email content."""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    data = request.json or {}
    html = data.get("html", "")
    if not html:
        return jsonify({"error": "No HTML provided"}), 400

    subject = data.get("subject", "Demo Email")
    sender = data.get("sender")
    original_id = data.get("original_id", f"demo_{uuid.uuid4()}")
    received_at_str = data.get("received_at")
    try:
        received_at = (
            date_parser.parse(received_at_str) if received_at_str else datetime.utcnow()
        )
    except Exception:
        received_at = datetime.utcnow()

    body_text = clean_email_body(parse_html_to_text(html))

    notification = crud.create_notification(
        db=g.db,
        subject=subject,
        received_at=received_at,
        original_email_id_str=original_id,
        sender=sender,
        email_body_text=body_text,
        email_body_html=html,
    )

    if not notification:
        return jsonify({"error": "Failed to create notification"}), 500

    llm_client = None
    if body_text and (
        config.settings.openai_api_key
        or config.settings.google_api_key
        or config.settings.groq_api_key
    ):
        try:
            llm_client = LLMFactory.get_llm_client()
        except Exception as e:
            logger.warning(f"LLM client creation failed: {e}")

    if llm_client and body_text:
        try:
            service_names = ", ".join(
                s.service_name for s in crud.get_external_services(g.db)
            )
            llm_response = analyze_with_voting(
                llm_client,
                text=body_text,
                prompt_template=INITIAL_EXTRACTION_PROMPT_TEMPLATE,
                email_subject=subject,
                email_body=body_text,
                service_options=service_names,
            )
            raw_llm_response = json.dumps(llm_response)
            if llm_response and not llm_response.get("error"):
                crud.update_llm_data_extracted_fields(
                    db=g.db,
                    llm_data_id=notification.llm_data_id,
                    extracted_service_name=llm_response.get("extracted_service_name"),
                    event_start_time=parse_llm_datetime(
                        llm_response.get("event_start_time")
                    ),
                    event_end_time=parse_llm_datetime(
                        llm_response.get("event_end_time")
                    ),
                    notification_type=parse_llm_notification_type(
                        llm_response.get("notification_type")
                    ),
                    severity=parse_llm_severity(llm_response.get("severity_level")),
                    llm_summary=llm_response.get("event_summary"),
                    raw_llm_response=raw_llm_response,
                    processing_status=ProcessingStatusEnum.COMPLETED,
                )
                crud.analyze_notification_impacts(
                    g.db, notification.id, llm_response.get("extracted_service_name")
                )
            else:
                crud.update_llm_data_status(
                    g.db,
                    notification.llm_data_id,
                    ProcessingStatusEnum.ERROR,
                    llm_response.get("error")
                    if isinstance(llm_response, dict)
                    else "LLM error",
                    raw_llm_response,
                )
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            crud.update_llm_data_status(
                g.db,
                notification.llm_data_id,
                ProcessingStatusEnum.ERROR,
                str(e),
            )

    return jsonify(serialize_notification(notification)), 201


# --- Parsing Helpers (from original file, slightly adapted) ---
def parse_llm_datetime(datetime_str: Optional[str]) -> Optional[datetime]:
    if not datetime_str or datetime_str.lower() == "null" or datetime_str.strip() == "":
        return None
    try:
        dt = date_parser.parse(datetime_str)
        return dt
    except (ValueError, TypeError, date_parser.ParserError) as e:
        logger.warning(f"Could not parse datetime string '{datetime_str}': {e}")
        return None


def parse_llm_notification_type(type_str: Optional[str]) -> NotificationTypeEnum:
    if not type_str or type_str.strip() == "":
        return NotificationTypeEnum.UNKNOWN
    processed_type_str = type_str.lower().strip()
    try:
        return NotificationTypeEnum(processed_type_str)
    except ValueError:
        maps = {
            "maintenance": NotificationTypeEnum.MAINTENANCE,
            "outage": NotificationTypeEnum.OUTAGE,
            "incident": NotificationTypeEnum.OUTAGE,
            "störung": NotificationTypeEnum.OUTAGE,
            "alert": NotificationTypeEnum.ALERT,
            "update": NotificationTypeEnum.INFO,
            "info": NotificationTypeEnum.INFO,
            "informational": NotificationTypeEnum.INFO,
            "resolved": NotificationTypeEnum.RESOLVED,
        }
        for key, val in maps.items():
            if key in processed_type_str:
                return val
        logger.warning(
            f"Unknown notification type string '{type_str}', defaulted to UNKNOWN."
        )
        return NotificationTypeEnum.UNKNOWN


def parse_llm_severity(severity_str: Optional[str]) -> SeverityEnum:
    if not severity_str or severity_str.strip() == "":
        return SeverityEnum.UNKNOWN
    processed_severity_str = severity_str.lower().strip()
    try:
        return SeverityEnum(processed_severity_str)
    except ValueError:
        maps = {
            "critical": SeverityEnum.CRITICAL,
            "high": SeverityEnum.HIGH,
            "medium": SeverityEnum.MEDIUM,
            "moderate": SeverityEnum.MEDIUM,
            "low": SeverityEnum.LOW,
            "informational": SeverityEnum.INFO,
            "info": SeverityEnum.INFO,
        }
        for key, val in maps.items():
            if key in processed_severity_str:
                return val
        logger.warning(
            f"Unknown severity string '{severity_str}', defaulted to UNKNOWN."
        )
        return SeverityEnum.UNKNOWN


def validate_llm_extraction_response(data: Dict[str, Any]) -> bool:
    required_keys = {
        "extracted_service_name",
        "event_start_time",
        "event_end_time",
        "notification_type",
        "event_summary",
        "severity_level",
    }
    if not isinstance(data, dict):
        return False
    if not required_keys.issubset(data.keys()):
        return False
    allowed_types = {
        "maintenance",
        "outage",
        "update",
        "alert",
        "info",
        "security",
        "unknown",
        None,
    }
    allowed_severities = {
        "low",
        "medium",
        "high",
        "critical",
        "info",
        "unknown",
        None,
    }
    nt = (data.get("notification_type") or "").lower() if data.get("notification_type") is not None else None
    sev = (data.get("severity_level") or "").lower() if data.get("severity_level") is not None else None
    if nt not in allowed_types:
        return False
    if sev not in allowed_severities:
        return False
    return True


def analyze_with_retry(
    llm_client: BaseLLM,
    *,
    text: str,
    prompt_template: str,
    max_attempts: int = 2,
    **kwargs,
) -> Dict[str, Any]:
    response: Dict[str, Any] = {}
    for attempt in range(max_attempts):
        response = llm_client.analyze_text(
            text=text,
            prompt_template=prompt_template,
            **kwargs,
        )
        if not response.get("error") and validate_llm_extraction_response(response):
            return response
        logger.warning(
            f"LLM response validation failed on attempt {attempt + 1}: {response}"
        )
    return response


def analyze_with_voting(
    llm_client: BaseLLM,
    *,
    text: str,
    prompt_template: str,
    votes: int = 3,
    **kwargs,
) -> Dict[str, Any]:
    """Run the LLM multiple times and return the most common extraction."""
    vote_results: List[Dict[str, Any]] = []
    for _ in range(votes):
        vote_results.append(
            analyze_with_retry(
                llm_client,
                text=text,
                prompt_template=prompt_template,
                **kwargs,
            )
        )

    valid = [r for r in vote_results if not r.get("error") and validate_llm_extraction_response(r)]
    if not valid:
        return vote_results[0] if vote_results else {}

    counts: Dict[str, int] = {}
    for r in valid:
        name = r.get("extracted_service_name")
        counts[name] = counts.get(name, 0) + 1

    majority = max(counts, key=counts.get)
    for r in valid:
        if r.get("extracted_service_name") == majority:
            return r
    return valid[0]


# --- Main Email Processing Workflow (adapted to run with its own DB session) ---
def main_email_processing_workflow():
    logger.info("NoticeHub main email processing workflow started.")
    db_session_local = get_db_session()
    llm_client = None
    try:
        if config.settings.llm_provider and (
            config.settings.openai_api_key or config.settings.google_api_key
        ):
            logger.info(
                f"Initializing LLM Client for provider: {config.settings.llm_provider}..."
            )
            llm_client = LLMFactory.get_llm_client()
            if llm_client:
                logger.info(f"LLM Client created for model: {llm_client.model_name}")
        else:
            logger.warning(
                "LLM provider or API key not configured. LLM processing will be skipped."
            )

        if not (
            config.settings.email_username
            and config.settings.email_password
            and config.settings.email_server
        ):
            logger.warning(
                "Email credentials/server not fully configured. Skipping email fetching."
            )
            return

        email_client = EmailClient(
            server=config.settings.email_server,
            port=config.settings.email_port,
            username=config.settings.email_username,
            password=config.settings.email_password,
            folder=config.settings.email_folder,
        )

        if not email_client.connect():
            logger.error("Failed to connect to email server. Aborting workflow loop.")
            return

        logger.info("Fetching unread emails...")
        unread_emails = email_client.get_unread_emails()
        logger.info(f"Found {len(unread_emails)} unread emails.")

        for raw_email_data in unread_emails:
            logger.info(
                f"Processing email ID {raw_email_data['id']}, Subject: '{raw_email_data['subject']}'"
            )
            existing_notification = crud.get_notification_by_original_email_id(
                db_session_local, raw_email_data["id"]
            )
            if existing_notification:
                logger.info(
                    f"Email ID {raw_email_data['id']} already processed. Skipping."
                )
                continue

            if not pre_filter_email(
                raw_email_data,
                sender_whitelist=SENDER_WHITELIST,
                sender_blacklist=SENDER_BLACKLIST,
                subject_keywords=SUBJECT_KEYWORDS,
            ):
                logger.info(
                    f"Email ID {raw_email_data['id']} did not pass pre-filters. Skipping."
                )
                continue

            # Use existing create_notification which now creates RawEmail and LLMData within a transaction
            notification_record = crud.create_notification(
                db=db_session_local,
                subject=raw_email_data["subject"],
                sender=raw_email_data["from"],
                email_body_text=raw_email_data["body_text"],
                email_body_html=raw_email_data["body_html"],
                original_email_id_str=raw_email_data["id"],  # Pass the string ID
                received_at=raw_email_data["date"] or datetime.utcnow(),
            )
            if not notification_record or not notification_record.llm_data:
                logger.error(
                    f"Failed to create notification record or LLMData for email ID {raw_email_data['id']}. Skipping LLM."
                )
                continue
            logger.info(
                f"Created Notification ID: {notification_record.id}, LLMData ID: {notification_record.llm_data.id}"
            )

            if not llm_client:
                logger.warning(
                    f"LLM client not available. Updating LLMData ID {notification_record.llm_data.id} to MANUAL_REVIEW."
                )
                crud.update_llm_data_status(
                    db_session_local,
                    notification_record.llm_data.id,
                    ProcessingStatusEnum.MANUAL_REVIEW,
                    "LLM client not available",
                )
                continue

            content_to_analyze = clean_email_body(raw_email_data["body_text"] or "")
            if not content_to_analyze:
                logger.warning(
                    f"Email ID {raw_email_data['id']} has no text body. Updating LLMData ID {notification_record.llm_data.id} to ERROR."
                )
                crud.update_llm_data_status(
                    db_session_local,
                    notification_record.llm_data.id,
                    ProcessingStatusEnum.ERROR,
                    "No text body for LLM analysis",
                )
                continue

            logger.info(
                f"Sending content for Notification ID {notification_record.id} to LLM..."
            )
            try:
                service_names = ", ".join(
                    s.service_name for s in crud.get_external_services(db_session_local)
                )
                llm_response_dict = analyze_with_voting(
                    llm_client,
                    text=content_to_analyze,
                    prompt_template=INITIAL_EXTRACTION_PROMPT_TEMPLATE,
                    email_subject=raw_email_data["subject"],
                    email_body=content_to_analyze,
                    service_options=service_names,
                )
                raw_llm_response_str = json.dumps(llm_response_dict)

                if llm_response_dict and not llm_response_dict.get("error"):
                    logger.info(
                        f"LLM analysis successful for LLMData ID {notification_record.llm_data.id}."
                    )
                    extracted_service_name = llm_response_dict.get(
                        "extracted_service_name"
                    )
                    parsed_start_time = parse_llm_datetime(
                        llm_response_dict.get("event_start_time")
                    )
                    parsed_end_time = parse_llm_datetime(
                        llm_response_dict.get("event_end_time")
                    )
                    parsed_notification_type = parse_llm_notification_type(
                        llm_response_dict.get("notification_type")
                    )
                    parsed_severity = parse_llm_severity(
                        llm_response_dict.get("severity_level")
                    )
                    event_summary_str = llm_response_dict.get("event_summary")

                    crud.update_llm_data_extracted_fields(
                        db=db_session_local,
                        llm_data_id=notification_record.llm_data.id,
                        extracted_service_name=extracted_service_name,
                        event_start_time=parsed_start_time,
                        event_end_time=parsed_end_time,
                        notification_type=parsed_notification_type,
                        severity=parsed_severity,
                        llm_summary=event_summary_str,
                        raw_llm_response=raw_llm_response_str,
                        processing_status=ProcessingStatusEnum.COMPLETED,  # Or PENDING_VALIDATION if needed
                    )

                    impacts = crud.analyze_notification_impacts(
                        db_session_local, notification_record.id, extracted_service_name
                    )
                    for imp in impacts:
                        logger.info(
                            f"Notification {notification_record.id} impacts internal system {imp.internal_system_id}"
                        )
                        if (
                            getattr(imp, "internal_system", None)
                            and imp.internal_system.responsible_contact
                        ):
                            send_email_notification(
                                imp.internal_system.responsible_contact,
                                f"Service issue: {extracted_service_name}",
                                event_summary_str or "Service notification",
                            )
                else:
                    err_msg = f"LLM error: {llm_response_dict.get('error', 'Unknown LLM error')}"
                    logger.error(
                        f"LLM analysis failed for LLMData ID {notification_record.llm_data.id}. {err_msg}"
                    )
                    crud.update_llm_data_status(
                        db_session_local,
                        notification_record.llm_data.id,
                        ProcessingStatusEnum.ERROR,
                        err_msg,
                        raw_llm_response_str,
                    )
            except Exception as e:
                logger.error(
                    f"Exception during LLM analysis for LLMData ID {notification_record.llm_data.id}: {e}",
                    exc_info=True,
                )
                crud.update_llm_data_status(
                    db_session_local,
                    notification_record.llm_data.id,
                    ProcessingStatusEnum.ERROR,
                    str(e),
                )

        if email_client and email_client.connection:
            email_client.disconnect()
    except Exception as e:
        logger.error(
            f"An error occurred in the main email processing workflow: {e}",
            exc_info=True,
        )
    finally:
        if db_session_local:
            db_session_local.close()
    logger.info("NoticeHub main email processing workflow finished iteration.")


# --- Database consistency check API ---
@app.route("/api/v1/admin/db-consistency-check", methods=["POST"])
def trigger_db_consistency_check():
    """API endpoint to manually trigger a database consistency check.
    
    This endpoint requires authentication in a production environment.
    """
    try:
        stats = crud.check_and_fix_data_consistency(g.db)
        return jsonify({"message": "Database consistency check completed", "stats": stats}), 200
    except Exception as e:
        logger.error(f"Error running database consistency check: {e}", exc_info=True)
        return jsonify({"error": "Failed to run database consistency check", "details": str(e)}), 500


# --- Background Thread for Email Processing ---
def run_email_processor_periodically():
    while True:
        try:
            main_email_processing_workflow()
        except Exception as e:
            logger.error(
                f"Unhandled exception in periodic email processor: {e}", exc_info=True
            )
        logger.info(
            f"Email processing iteration complete. Waiting {config.settings.email_check_interval_seconds}s."
        )
        time.sleep(config.settings.email_check_interval_seconds)


# --- Background Thread for Database Consistency Check ---
def run_db_consistency_check_periodically():
    """Run database consistency checks periodically to fix inconsistencies."""
    # Wait a bit on startup to let other processes initialize
    time.sleep(60)  
    
    # Run every hour by default, or use configuration if available
    consistency_check_interval = getattr(config.settings, 'db_consistency_check_interval_seconds', 3600)
    
    logger.info(f"Database consistency checker started, will run every {consistency_check_interval} seconds")
    
    while True:
        try:
            logger.info("Running scheduled database consistency check")
            db_session = get_db_session()
            try:
                stats = crud.check_and_fix_data_consistency(db_session)
                if stats["fixed_issues"] > 0:
                    logger.info(f"Scheduled consistency check fixed {stats['fixed_issues']} issues")
            finally:
                db_session.close()
        except Exception as e:
            logger.error(f"Error in scheduled database consistency check: {e}", exc_info=True)
        
        # Sleep until next check
        logger.info(f"Next database consistency check in {consistency_check_interval} seconds")
        time.sleep(consistency_check_interval)


# --- Application Initialization ---
def initialize_database():
    logger.info("Creating database tables if they don't exist...")
    try:
        create_tables()
        logger.info("Database tables checked/created successfully.")
        db = get_db_session()
        try:
            seed_demo_data(db)
        finally:
            db.close()
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        initialize_database()

        logger.info("Starting email processing background thread...")
        email_thread = threading.Thread(
            target=run_email_processor_periodically, daemon=True
        )
        email_thread.start()
        
        logger.info("Starting database consistency checker background thread...")
        db_check_thread = threading.Thread(
            target=run_db_consistency_check_periodically, daemon=True
        )
        db_check_thread.start()

        logger.info(f"Starting Flask API server on port 5001...")
        app.run(host="0.0.0.0", port=5001, debug=config.settings.debug_mode)

    except Exception as e:
        logger.critical(f"Application failed to start: {e}", exc_info=True)
    finally:
        logger.info("NoticeHub application shutting down.")
