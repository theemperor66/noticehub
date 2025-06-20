import json
import os
import uuid
from datetime import datetime
from typing import Optional

from dateutil import parser as date_parser
from sqlalchemy.orm import Session

from src.config import PROJECT_ROOT
from src.utils.logger import logger
from src.data import crud
from src.data.models import (
    Notification,
    NotificationStatusEnum,
    ProcessingStatusEnum,
    NotificationTypeEnum,
    SeverityEnum,
)


def _parse_notification_type(type_str: Optional[str]) -> NotificationTypeEnum:
    if not type_str or type_str.strip() == "":
        return NotificationTypeEnum.UNKNOWN
    processed = type_str.lower().strip()
    try:
        return NotificationTypeEnum(processed)
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
            "degradation": NotificationTypeEnum.ALERT,
        }
        for key, val in maps.items():
            if key in processed:
                return val
        return NotificationTypeEnum.UNKNOWN


def _parse_severity(severity_str: Optional[str]) -> SeverityEnum:
    if not severity_str or severity_str.strip() == "":
        return SeverityEnum.UNKNOWN
    processed = severity_str.lower().strip()
    try:
        return SeverityEnum(processed)
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
            if key in processed:
                return val
        return SeverityEnum.UNKNOWN


def seed_demo_data(db: Session, json_path: Optional[str] = None) -> None:
    """Populate the database with demo data if empty."""
    if json_path is None:
        json_path = os.path.join(PROJECT_ROOT, "scripts", "demo_data.json")

    if db.query(Notification).first():
        logger.info("Database already seeded; skipping demo data load.")
        return

    try:
        with open(json_path) as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load demo data from {json_path}: {e}")
        return

    svc_map = {}
    for svc in data.get("external_services", []):
        svc_obj = crud.create_external_service(
            db,
            service_name=svc.get("service_name"),
            provider=svc.get("provider"),
            description=svc.get("description"),
        )
        svc_map[svc.get("service_name")] = svc_obj

    sys_map = {}
    for sys in data.get("internal_systems", []):
        sys_obj = crud.create_internal_system(
            db,
            system_name=sys.get("system_name"),
            responsible_contact=sys.get("responsible_contact"),
            description=sys.get("description"),
        )
        sys_map[sys.get("system_name")] = sys_obj

    for dep in data.get("dependencies", []):
        is_name = dep.get("internal_system", {}).get("system_name")
        es_name = dep.get("external_service", {}).get("service_name")
        if not is_name or not es_name:
            continue
        crud.create_dependency(
            db,
            internal_system_id=sys_map[is_name].id,
            external_service_id=svc_map[es_name].id,
            dependency_description=dep.get("dependency_description"),
        )

    for notif in data.get("notifications", []):
        created = notif.get("created_at")
        created_dt = (
            date_parser.parse(created) if created else datetime.utcnow()
        )
        n = crud.create_notification(
            db,
            subject=notif.get("title", "Demo Notification"),
            received_at=created_dt,
            original_email_id_str=f"demo_seed_{uuid.uuid4()}",
            sender="demo@noticehub.local",
            email_body_text=notif.get("llm_data", {}).get("llm_summary"),
        )
        if not n:
            continue
        llm = notif.get("llm_data", {})
        crud.update_llm_data_extracted_fields(
            db,
            llm_data_id=n.llm_data_id,
            extracted_service_name=llm.get("extracted_service_name"),
            event_start_time=None,
            event_end_time=None,
            notification_type=_parse_notification_type(
                llm.get("notification_type")
            ),
            severity=_parse_severity(llm.get("severity")),
            llm_summary=llm.get("llm_summary"),
            raw_llm_response=None,
            processing_status=ProcessingStatusEnum(
                llm.get("processing_status", "completed")
            ),
        )
        status_raw = (notif.get("status") or "new").lower()
        try:
            n.status = NotificationStatusEnum(status_raw)
        except ValueError:
            mappings = {
                "investigating": NotificationStatusEnum.IN_PROGRESS,
                "resolved": NotificationStatusEnum.RESOLVED,
            }
            n.status = mappings.get(status_raw, NotificationStatusEnum.NEW)
        db.commit()
        crud.analyze_notification_impacts(db, n.id, llm.get("extracted_service_name"))
        db.refresh(n)


