import json
import os
import uuid
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from dateutil import parser as date_parser
from sqlalchemy.orm import Session

from src.config import PROJECT_ROOT
from src.data import crud
from src.data.models import (
    Notification,
    NotificationStatusEnum,
    NotificationTypeEnum,
    ProcessingStatusEnum,
    SeverityEnum,
)
from src.utils.logger import logger


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

    created_notifications = []
    for notif in data.get("notifications", []):
        created = notif.get("created_at")
        created_dt = date_parser.parse(created) if created else datetime.utcnow()
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
            notification_type=_parse_notification_type(llm.get("notification_type")),
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
        created_notifications.append((n, llm))

    # Instead of using the notification data directly, let's create a realistic
    # history of downtime events based on current time
    
    # Generate realistic downtime history for each service
    # Start with events from the last 30 days
    now = datetime.now(timezone.utc)
    services = list(svc_map.values())  # All available services
    
    # Create a realistic downtime history pattern for each service
    for service in services:
        # Determine how many events to create for this service (1-4)
        event_count = random.randint(1, 4)
        logger.info(f"Creating {event_count} downtime events for {service.service_name}")
        
        for i in range(event_count):
            # Choose a notification to associate with this event
            n, llm = random.choice(created_notifications)
            
            # Generate a start time within the last 30 days
            days_ago = random.randint(1, 30)
            hours_ago = random.randint(1, 23)
            minutes_ago = random.randint(1, 59)
            
            # Create start time: between 1-30 days ago
            start_time = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
            
            # Most events should be resolved, some should be ongoing
            is_resolved = random.random() > 0.2  # 80% are resolved
            
            # For resolved events, create realistic downtime duration
            if is_resolved:
                # Most issues resolve within a few hours
                # Distribution: 40% < 30min, 30% 30min-2h, 20% 2h-6h, 10% 6h-24h
                duration_probability = random.random()
                
                if duration_probability < 0.4:
                    # Short outage: 5-30 minutes
                    duration_minutes = random.randint(5, 30)
                elif duration_probability < 0.7:
                    # Medium outage: 30min-2h
                    duration_minutes = random.randint(30, 120)
                elif duration_probability < 0.9:
                    # Long outage: 2h-6h
                    duration_minutes = random.randint(120, 360)
                else:
                    # Extended outage: 6h-24h
                    duration_minutes = random.randint(360, 1440)
                
                end_time = start_time + timedelta(minutes=duration_minutes)
            else:
                # Ongoing event - no end time
                end_time = None
            
            # Pick a reasonable severity based on duration
            if is_resolved and duration_minutes < 30:
                severity = SeverityEnum.LOW
            elif is_resolved and duration_minutes < 120:
                severity = SeverityEnum.MEDIUM
            else:
                severity = SeverityEnum.HIGH
                
            # Create a realistic summary based on the service
            summaries = [
                f"Increased latency observed on {service.service_name}",
                f"Service degradation affecting {service.service_name}",
                f"Connectivity issues with {service.service_name}",
                f"Performance degradation in {service.service_name}",
                f"Partial outage affecting {service.service_name}",
                f"{service.service_name} experiencing increased error rates"
            ]
            summary = random.choice(summaries)
            
            # Create the downtime event
            event = crud.create_downtime_event(
                db,
                external_service_id=service.id,
                start_notification_id=n.id,
                start_time=start_time,
                severity=severity,
                summary=summary
            )
            
            # Close the event if it's resolved
            if is_resolved and end_time:
                crud.close_downtime_event(
                    db,
                    event_id=event.id,
                    end_notification_id=n.id,  # Use same notification for demo
                    end_time=end_time
                )
        
        # Ensure each service has at least one entry in the stats
        if event_count == 0:
            # Create a single short resolved event
            n, llm = random.choice(created_notifications)
            start_time = now - timedelta(days=random.randint(1, 10), hours=random.randint(1, 12))
            end_time = start_time + timedelta(minutes=random.randint(10, 60))  
            
            event = crud.create_downtime_event(
                db,
                external_service_id=service.id,
                start_notification_id=n.id,
                start_time=start_time,
                severity=SeverityEnum.LOW,
                summary=f"Minor disruption in {service.service_name}"
            )
            
            crud.close_downtime_event(
                db,
                event_id=event.id,
                end_notification_id=n.id,
                end_time=end_time
            )
