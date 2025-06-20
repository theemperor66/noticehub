from sqlalchemy.orm import Session, joinedload, Query
from typing import List, Optional  # Ensure List and Optional are imported

from src.utils.logger import logger  # Ensure logger is imported
from .models import (
    Notification,
    RawEmail,
    LLMData,
    NotificationStatusEnum,
    ProcessingStatusEnum,
    NotificationTypeEnum,
    SeverityEnum,
    ExternalService,
    InternalSystem,
    Dependency,
    NotificationImpact,
)
from typing import (
    Type,
    TypeVar,
    Any,
)  # Retaining these just in case, though List and Optional are primary
from datetime import datetime, timezone
import hashlib

from src.data.models import (
    Base,
    Notification,
    ExternalService,
    InternalSystem,
    Dependency,
    RawEmail,
    LLMData,
    ProcessingStatusEnum,
    NotificationTypeEnum,
    SeverityEnum,
    NotificationStatusEnum,
)
from src.utils.logger import logger

ModelType = TypeVar("ModelType", bound=Base)


def _get_query_with_options(
    db: Session, model_cls: Type[ModelType], options: Optional[List[Any]] = None
) -> Query:
    query = db.query(model_cls)
    if options:
        for option in options:
            query = query.options(option)
    return query


def get_item_by_id(
    db: Session,
    model: Type[ModelType],
    item_id: int,
    options: Optional[List[Any]] = None,
) -> Optional[ModelType]:
    """Generic function to get an item by its ID, with support for SQLAlchemy load options."""
    query = _get_query_with_options(db, model, options)
    return query.filter(model.id == item_id).first()


# --- Notifications, RawEmail, LLMData CRUD --- #


def create_notification(
    db: Session,
    subject: str,
    received_at: datetime,
    original_email_id_str: str,
    sender: Optional[str] = None,
    email_body_text: Optional[str] = None,
    email_body_html: Optional[str] = None,
) -> Optional[Notification]:
    """Creates RawEmail, LLMData, and Notification records from an incoming email."""
    try:
        # 1. Create RawEmail
        hashed_email_id = hashlib.sha256(original_email_id_str.encode()).hexdigest()
        db_raw_email = RawEmail(
            original_email_id_hash=hashed_email_id,
            subject=subject,
            sender=sender,
            received_at=received_at,
            body_text=email_body_text,
            body_html=email_body_html,
            has_html_body=bool(email_body_html),
        )
        db.add(db_raw_email)
        # We need the ID of db_raw_email for the Notification, so flush to get it.
        db.flush()

        # 2. Create LLMData
        db_llm_data = LLMData(processing_status=ProcessingStatusEnum.UNPROCESSED)
        db.add(db_llm_data)
        # We need the ID of db_llm_data for the Notification, so flush to get it.
        db.flush()

        # 3. Create Notification
        db_notification = Notification(
            title=subject,  # Use email subject as initial title
            status=NotificationStatusEnum.NEW,  # Initial status
            raw_email_id=db_raw_email.id,
            llm_data_id=db_llm_data.id,
            last_checked_at=datetime.now(timezone.utc),  # Or received_at
        )
        db.add(db_notification)

        db.commit()
        db.refresh(db_raw_email)
        db.refresh(db_llm_data)
        db.refresh(db_notification)
        logger.info(
            f"Created Notification ID {db_notification.id} (RawEmail ID: {db_raw_email.id}, LLMData ID: {db_llm_data.id}) for original email hash {hashed_email_id}"
        )
        return db_notification
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error creating notification for original_email_id_str {original_email_id_str}: {e}",
            exc_info=True,
        )
        return None


def _map_llm_status_to_notification_status(
    llm_processing_status: ProcessingStatusEnum,
) -> NotificationStatusEnum:
    if llm_processing_status == ProcessingStatusEnum.COMPLETED:
        return NotificationStatusEnum.TRIAGED
    elif llm_processing_status == ProcessingStatusEnum.ERROR:
        return NotificationStatusEnum.ERROR_PROCESSING
    elif llm_processing_status == ProcessingStatusEnum.MANUAL_REVIEW:
        return NotificationStatusEnum.PENDING_MANUAL_REVIEW  # Assuming this exists
    elif llm_processing_status == ProcessingStatusEnum.PENDING_VALIDATION:
        return NotificationStatusEnum.PENDING_VALIDATION  # Assuming this exists
    return NotificationStatusEnum.NEW  # Default or UNPROCESSED equivalent


def update_llm_data_extracted_fields(
    db: Session,
    llm_data_id: int,
    extracted_service_name: Optional[str],
    event_start_time: Optional[datetime],
    event_end_time: Optional[datetime],
    notification_type: Optional[NotificationTypeEnum],
    severity: Optional[SeverityEnum],
    llm_summary: Optional[str],
    raw_llm_response: Optional[str],
    processing_status: ProcessingStatusEnum,
) -> Optional[LLMData]:
    """Updates LLMData with extracted fields and updates parent Notification status."""
    db_llm_data = get_item_by_id(db, LLMData, llm_data_id)
    if not db_llm_data:
        logger.warning(f"LLMData ID {llm_data_id} not found for update.")
        return None

    db_llm_data.extracted_service_name = extracted_service_name
    db_llm_data.event_start_time = event_start_time
    db_llm_data.event_end_time = event_end_time
    db_llm_data.notification_type = notification_type
    db_llm_data.severity = severity
    db_llm_data.llm_summary = llm_summary
    db_llm_data.raw_llm_response = raw_llm_response
    db_llm_data.processing_status = processing_status
    db_llm_data.error_message = None  # Clear previous errors if successfully processed

    # Update parent Notification status
    notification = (
        db.query(Notification)
        .filter(Notification.llm_data_id == llm_data_id)
        .options(joinedload(Notification.llm_data))
        .first()
    )
    if notification:
        notification.status = _map_llm_status_to_notification_status(processing_status)
        notification.last_checked_at = datetime.now(timezone.utc)
        logger.info(
            f"Parent Notification ID {notification.id} status updated to {notification.status.value}"
        )
    else:
        logger.warning(
            f"Could not find parent Notification for LLMData ID {llm_data_id} to update status."
        )

    try:
        db.commit()
        db.refresh(db_llm_data)
        if notification:
            db.refresh(notification)
        logger.info(
            f"Updated LLMData ID {llm_data_id}. Status: {processing_status.value}"
        )
        return db_llm_data
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating LLMData ID {llm_data_id}: {e}", exc_info=True)
        return None


def update_llm_data_status(
    db: Session,
    llm_data_id: int,
    processing_status: ProcessingStatusEnum,
    error_message: Optional[str] = None,
    raw_llm_response: Optional[
        str
    ] = None,  # Store raw response even on error if available
) -> Optional[LLMData]:
    """Updates the processing status and error message of an LLMData record, and parent Notification."""
    db_llm_data = get_item_by_id(db, LLMData, llm_data_id)
    if not db_llm_data:
        logger.warning(f"LLMData ID {llm_data_id} not found for status update.")
        return None

    db_llm_data.processing_status = processing_status
    db_llm_data.error_message = error_message
    if raw_llm_response is not None:  # Only update if provided
        db_llm_data.raw_llm_response = raw_llm_response

    # Update parent Notification status
    notification = (
        db.query(Notification)
        .filter(Notification.llm_data_id == llm_data_id)
        .options(joinedload(Notification.llm_data))
        .first()
    )
    if notification:
        notification.status = _map_llm_status_to_notification_status(processing_status)
        notification.last_checked_at = datetime.now(timezone.utc)
        logger.info(
            f"Parent Notification ID {notification.id} status updated to {notification.status.value} due to LLMData status change."
        )
    else:
        logger.warning(
            f"Could not find parent Notification for LLMData ID {llm_data_id} to update status."
        )

    try:
        db.commit()
        db.refresh(db_llm_data)
        if notification:
            db.refresh(notification)
        logger.info(
            f"Updated LLMData ID {llm_data_id} status to {processing_status.value}."
        )
        return db_llm_data
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error updating LLMData ID {llm_data_id} status: {e}", exc_info=True
        )
        return None


def get_notification_by_original_email_id(
    db: Session, original_email_id_str: str, options: Optional[List[Any]] = None
) -> Optional[Notification]:
    hashed_email_id = hashlib.sha256(original_email_id_str.encode()).hexdigest()
    raw_email = (
        db.query(RawEmail)
        .filter(RawEmail.original_email_id_hash == hashed_email_id)
        .first()
    )
    if raw_email:
        query = _get_query_with_options(db, Notification, options)
        return query.filter(Notification.raw_email_id == raw_email.id).first()
    return None


def get_notifications(
    db: Session, skip: int = 0, limit: int = 100, options: Optional[List[Any]] = None
) -> List[Notification]:
    """Retrieves a list of notifications with pagination and loading options."""
    query = _get_query_with_options(db, Notification, options)
    return (
        query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()
    )


def get_notification(
    db: Session, notification_id: int, options: Optional[List[Any]] = None
) -> Optional[Notification]:
    """Retrieves a single notification by its ID with loading options."""
    return get_item_by_id(db, Notification, notification_id, options=options)


def get_pending_notifications(
    db: Session, limit: int = 10, options: Optional[List[Any]] = None
) -> List[Notification]:
    """Retrieves notifications whose LLMData is UNPROCESSED or PENDING_VALIDATION."""
    query = _get_query_with_options(db, Notification, options)
    return (
        query.join(Notification.llm_data)
        .filter(
            LLMData.processing_status.in_(
                [
                    ProcessingStatusEnum.UNPROCESSED,
                    ProcessingStatusEnum.PENDING_VALIDATION,
                ]
            )
        )
        .order_by(Notification.created_at.asc())
        .limit(limit)
        .all()
    )


def delete_notification(db: Session, notification_id: int) -> bool:
    """Deletes a notification and its related data."""
    notification = (
        db.query(Notification).filter(Notification.id == notification_id).first()
    )
    if not notification:
        logger.warning(
            f"Notification with ID {notification_id} not found for deletion."
        )
        return False
    try:
        db.query(NotificationImpact).filter(
            NotificationImpact.notification_id == notification_id
        ).delete()
        db.delete(notification)
        db.commit()
        logger.info(f"Successfully deleted notification ID {notification_id}.")
        return True
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error deleting notification ID {notification_id}: {e}",
            exc_info=True,
        )
        return False


# --- ExternalService CRUD Operations ---


def create_external_service(
    db: Session,
    service_name: str,
    provider: Optional[str] = None,
    description: Optional[str] = None,
) -> ExternalService:
    """
    Creates a new external service.
    Checks if a service with the same name already exists.
    """
    existing_service = (
        db.query(ExternalService)
        .filter(ExternalService.service_name == service_name)
        .first()
    )
    if existing_service:
        logger.warning(
            f"Attempted to create an external service with a name that already exists: '{service_name}' (Existing ID: {existing_service.id}). Returning existing service."
        )
        return existing_service

    db_external_service = ExternalService(
        service_name=service_name, provider=provider, description=description
    )
    db.add(db_external_service)
    db.commit()
    db.refresh(db_external_service)
    logger.info(
        f"Created external service '{db_external_service.service_name}' with ID {db_external_service.id}."
    )
    return db_external_service


def get_external_service(db: Session, service_id: int) -> Optional[ExternalService]:
    """
    Retrieves an external service by its ID.
    """
    service = db.query(ExternalService).filter(ExternalService.id == service_id).first()
    if not service:
        logger.debug(f"External service with ID {service_id} not found.")
    return service


def get_external_service_by_name(
    db: Session, service_name: str
) -> Optional[ExternalService]:
    """
    Retrieves an external service by its unique name.
    """
    service = (
        db.query(ExternalService)
        .filter(ExternalService.service_name == service_name)
        .first()
    )
    if not service:
        logger.debug(f"External service with name '{service_name}' not found.")
    return service


def get_external_services(
    db: Session, skip: int = 0, limit: int = 100
) -> List[ExternalService]:
    """
    Retrieves a list of external services with pagination, ordered by service_name.
    """
    return (
        db.query(ExternalService)
        .order_by(ExternalService.service_name)
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_external_service(
    db: Session,
    service_id: int,
    service_name: Optional[str] = None,
    provider: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[ExternalService]:
    """
    Updates an existing external service.
    Only updates fields that are provided.
    Checks for service_name uniqueness if it's being changed.
    """
    db_external_service = (
        db.query(ExternalService).filter(ExternalService.id == service_id).first()
    )
    if not db_external_service:
        logger.warning(f"External service with ID {service_id} not found for update.")
        return None

    update_data_dict = {}
    if service_name is not None:
        update_data_dict["service_name"] = service_name
    if provider is not None:
        update_data_dict["provider"] = provider
    if description is not None:
        update_data_dict["description"] = description

    if not update_data_dict:
        logger.info(f"No update data provided for external service ID {service_id}.")
        return db_external_service

    if (
        "service_name" in update_data_dict
        and update_data_dict["service_name"] != db_external_service.service_name
    ):
        existing_service_with_new_name = (
            db.query(ExternalService)
            .filter(
                ExternalService.service_name == update_data_dict["service_name"],
                ExternalService.id != service_id,
            )
            .first()
        )
        if existing_service_with_new_name:
            logger.error(
                f"Cannot update external service ID {service_id}: "
                f"another service with name '{update_data_dict['service_name']}' already exists (ID: {existing_service_with_new_name.id})."
            )
            return None

    for key, value in update_data_dict.items():
        setattr(db_external_service, key, value)

    try:
        db.commit()
        db.refresh(db_external_service)
        logger.info(f"Successfully updated external service ID {service_id}.")
        return db_external_service
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error updating external service ID {service_id}: {e}", exc_info=True
        )
        return None


def delete_external_service(db: Session, service_id: int) -> bool:
    """
    Deletes an external service by its ID.
    Returns True if deletion was successful, False otherwise.
    Prevents deletion if the service is linked to any dependencies.
    """
    db_external_service = (
        db.query(ExternalService)
        .options(joinedload(ExternalService.dependencies))
        .filter(ExternalService.id == service_id)
        .first()
    )

    if not db_external_service:
        logger.warning(f"External service with ID {service_id} not found for deletion.")
        return False

    if db_external_service.dependencies:
        logger.error(
            f"Cannot delete external service ID {service_id} ('{db_external_service.service_name}') as it is linked to "
            f"{len(db_external_service.dependencies)} dependencies. Please remove these dependencies first."
        )
        return False

    try:
        db.delete(db_external_service)
        db.commit()
        logger.info(
            f"Successfully deleted external service ID {service_id} ('{db_external_service.service_name}')."
        )
        return True
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error deleting external service ID {service_id}: {e}", exc_info=True
        )
        return False


# --- InternalSystem CRUD Operations ---


def create_internal_system(
    db: Session,
    system_name: str,
    responsible_contact: Optional[str] = None,
    description: Optional[str] = None,
) -> InternalSystem:
    """
    Creates a new internal system.
    Checks if a system with the same name already exists.
    """
    existing_system = (
        db.query(InternalSystem)
        .filter(InternalSystem.system_name == system_name)
        .first()
    )
    if existing_system:
        logger.warning(
            f"Attempted to create an internal system with a name that already exists: '{system_name}' (Existing ID: {existing_system.id}). Returning existing system."
        )
        return existing_system

    db_internal_system = InternalSystem(
        system_name=system_name,
        responsible_contact=responsible_contact,
        description=description,
    )
    db.add(db_internal_system)
    db.commit()
    db.refresh(db_internal_system)
    logger.info(
        f"Created internal system '{db_internal_system.system_name}' with ID {db_internal_system.id}."
    )
    return db_internal_system


def get_internal_system(db: Session, system_id: int) -> Optional[InternalSystem]:
    """
    Retrieves an internal system by its ID.
    """
    system = db.query(InternalSystem).filter(InternalSystem.id == system_id).first()
    if not system:
        logger.debug(f"Internal system with ID {system_id} not found.")
    return system


def get_internal_system_by_name(
    db: Session, system_name: str
) -> Optional[InternalSystem]:
    """
    Retrieves an internal system by its unique name.
    """
    system = (
        db.query(InternalSystem)
        .filter(InternalSystem.system_name == system_name)
        .first()
    )
    if not system:
        logger.debug(f"Internal system with name '{system_name}' not found.")
    return system


def get_internal_systems(
    db: Session, skip: int = 0, limit: int = 100
) -> List[InternalSystem]:
    """
    Retrieves a list of internal systems with pagination, ordered by system_name.
    """
    return (
        db.query(InternalSystem)
        .order_by(InternalSystem.system_name)
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_internal_system(
    db: Session,
    system_id: int,
    system_name: Optional[str] = None,
    responsible_contact: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[InternalSystem]:
    """
    Updates an existing internal system.
    Only updates fields that are provided.
    Checks for system_name uniqueness if it's being changed.
    """
    db_internal_system = (
        db.query(InternalSystem).filter(InternalSystem.id == system_id).first()
    )
    if not db_internal_system:
        logger.warning(f"Internal system with ID {system_id} not found for update.")
        return None

    update_data_dict = {}
    if system_name is not None:
        update_data_dict["system_name"] = system_name
    if responsible_contact is not None:
        update_data_dict["responsible_contact"] = responsible_contact
    if description is not None:
        update_data_dict["description"] = description

    if not update_data_dict:
        logger.info(f"No update data provided for internal system ID {system_id}.")
        return db_internal_system

    if (
        "system_name" in update_data_dict
        and update_data_dict["system_name"] != db_internal_system.system_name
    ):
        existing_system_with_new_name = (
            db.query(InternalSystem)
            .filter(
                InternalSystem.system_name == update_data_dict["system_name"],
                InternalSystem.id != system_id,
            )
            .first()
        )
        if existing_system_with_new_name:
            logger.error(
                f"Cannot update internal system ID {system_id}: "
                f"another system with name '{update_data_dict['system_name']}' already exists (ID: {existing_system_with_new_name.id})."
            )
            return None

    for key, value in update_data_dict.items():
        setattr(db_internal_system, key, value)

    try:
        db.commit()
        db.refresh(db_internal_system)
        logger.info(f"Successfully updated internal system ID {system_id}.")
        return db_internal_system
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error updating internal system ID {system_id}: {e}", exc_info=True
        )
        return None


def delete_internal_system(db: Session, system_id: int) -> bool:
    """
    Deletes an internal system by its ID.
    Returns True if deletion was successful, False otherwise.
    Prevents deletion if the system is linked to any dependencies.
    """
    db_internal_system = (
        db.query(InternalSystem)
        .options(joinedload(InternalSystem.dependencies))
        .filter(InternalSystem.id == system_id)
        .first()
    )

    if not db_internal_system:
        logger.warning(f"Internal system with ID {system_id} not found for deletion.")
        return False

    if db_internal_system.dependencies:
        logger.error(
            f"Cannot delete internal system ID {system_id} ('{db_internal_system.system_name}') as it is linked to "
            f"{len(db_internal_system.dependencies)} dependencies. Please remove these dependencies first."
        )
        return False

    try:
        db.delete(db_internal_system)
        db.commit()
        logger.info(
            f"Successfully deleted internal system ID {system_id} ('{db_internal_system.system_name}')."
        )
        return True
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error deleting internal system ID {system_id}: {e}", exc_info=True
        )
        return False


# --- Dependency CRUD Operations ---


def get_dependency(db: Session, dependency_id: int) -> Optional[Dependency]:
    """Retrieves a dependency by its ID, eager loading related system and service."""
    dep = (
        db.query(Dependency)
        .options(
            joinedload(Dependency.internal_system),
            joinedload(Dependency.external_service),
        )
        .filter(Dependency.id == dependency_id)
        .first()
    )
    if not dep:
        logger.debug(f"Dependency with ID {dependency_id} not found.")
    return dep


def get_dependencies(db: Session, skip: int = 0, limit: int = 100) -> List[Dependency]:
    """Retrieves a list of all dependencies with pagination, eager loading related system and service."""
    return (
        db.query(Dependency)
        .options(
            joinedload(Dependency.internal_system),
            joinedload(Dependency.external_service),
        )
        .order_by(Dependency.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_dependencies_for_internal_system(
    db: Session, internal_system_id: int, skip: int = 0, limit: int = 100
) -> List[Dependency]:
    """Retrieves dependencies for a specific internal system with pagination, eager loading external services."""
    internal_system = get_internal_system(db, internal_system_id)
    if not internal_system:
        logger.warning(
            f"Cannot get dependencies: InternalSystem with ID {internal_system_id} not found."
        )
        return []

    return (
        db.query(Dependency)
        .options(joinedload(Dependency.external_service))
        .filter(Dependency.internal_system_id == internal_system_id)
        .order_by(Dependency.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_dependencies_for_external_service(
    db: Session, external_service_id: int, skip: int = 0, limit: int = 100
) -> List[Dependency]:
    """Retrieves dependencies for a specific external service with pagination, eager loading internal systems."""
    external_service = get_external_service(db, external_service_id)
    if not external_service:
        logger.warning(
            f"Cannot get dependencies: ExternalService with ID {external_service_id} not found."
        )
        return []

    return (
        db.query(Dependency)
        .options(joinedload(Dependency.internal_system))
        .filter(Dependency.external_service_id == external_service_id)
        .order_by(Dependency.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_dependency(
    db: Session,
    internal_system_id: int,
    external_service_id: int,
    dependency_description: Optional[str] = None,
) -> Optional[Dependency]:
    """
    Creates a new dependency between an internal system and an external service.
    Checks if the internal system and external service exist.
    Checks if a dependency with the same internal_system_id and external_service_id already exists.
    """
    internal_system = get_internal_system(db, internal_system_id)
    if not internal_system:
        logger.error(
            f"Cannot create dependency: InternalSystem with ID {internal_system_id} not found."
        )
        return None

    external_service = get_external_service(db, external_service_id)
    if not external_service:
        logger.error(
            f"Cannot create dependency: ExternalService with ID {external_service_id} not found."
        )
        return None

    existing_dependency = (
        db.query(Dependency)
        .filter_by(
            internal_system_id=internal_system_id,
            external_service_id=external_service_id,
        )
        .first()
    )

    if existing_dependency:
        logger.warning(
            f"Dependency between InternalSystem ID {internal_system_id} ('{internal_system.system_name}') and "
            f"ExternalService ID {external_service_id} ('{external_service.service_name}') already exists "
            f"(Dependency ID: {existing_dependency.id}). Returning existing dependency."
        )
        return existing_dependency

    db_dependency = Dependency(
        internal_system_id=internal_system_id,
        external_service_id=external_service_id,
        dependency_description=dependency_description,
    )
    db.add(db_dependency)
    db.commit()
    db.refresh(db_dependency)
    logger.info(
        f"Created dependency (ID: {db_dependency.id}) between InternalSystem ID {internal_system_id} "
        f"('{internal_system.system_name}') and ExternalService ID {external_service_id} ('{external_service.service_name}')."
    )
    return db_dependency


def update_dependency(
    db: Session, dependency_id: int, dependency_description: Optional[str] = None
) -> Optional[Dependency]:
    """
    Updates an existing dependency, primarily its description.
    """
    db_dependency = db.query(Dependency).filter(Dependency.id == dependency_id).first()
    if not db_dependency:
        logger.warning(f"Dependency with ID {dependency_id} not found for update.")
        return None

    updated = False
    if (
        dependency_description is not None
        and db_dependency.dependency_description != dependency_description
    ):
        db_dependency.dependency_description = dependency_description
        updated = True

    if updated:
        try:
            db.commit()
            db.refresh(db_dependency)
            logger.info(f"Successfully updated dependency ID {dependency_id}.")
        except Exception as e:
            db.rollback()
            logger.error(
                f"Error updating dependency ID {dependency_id}: {e}", exc_info=True
            )
            return None
    else:
        logger.info(
            f"No update data (description) provided or data matches existing for dependency ID {dependency_id}."
        )

    return db_dependency


def delete_dependency(db: Session, dependency_id: int) -> bool:
    """Deletes a dependency by its ID."""
    db_dependency = db.query(Dependency).filter(Dependency.id == dependency_id).first()
    if not db_dependency:
        logger.warning(f"Dependency with ID {dependency_id} not found for deletion.")
        return False
    try:
        db.delete(db_dependency)
        db.commit()
        logger.info(f"Successfully deleted dependency ID {dependency_id}.")
        return True
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error deleting dependency ID {dependency_id}: {e}", exc_info=True
        )
        return False


# --- Notification Impact Analysis ---
def create_notification_impact(
    db: Session, notification_id: int, internal_system_id: int
) -> Optional[NotificationImpact]:
    existing = (
        db.query(NotificationImpact)
        .filter_by(
            notification_id=notification_id, internal_system_id=internal_system_id
        )
        .first()
    )
    if existing:
        return existing
    impact = NotificationImpact(
        notification_id=notification_id, internal_system_id=internal_system_id
    )
    db.add(impact)
    db.commit()
    db.refresh(impact)
    return impact


def analyze_notification_impacts(
    db: Session, notification_id: int, service_name: Optional[str]
) -> List[NotificationImpact]:
    if not service_name:
        return []
    service = get_external_service_by_name(db, service_name)
    if not service:
        return []
    deps = get_dependencies_for_external_service(db, service.id)
    impacts: List[NotificationImpact] = []
    for dep in deps:
        impact = create_notification_impact(db, notification_id, dep.internal_system_id)
        impact.internal_system = dep.internal_system
        impacts.append(impact)
    return impacts

    # This try/except block belongs to delete_dependency


if __name__ == "__main__":
    from src.data.models import get_db_session, create_tables

    logger.info("Running CRUD operations test (new structure)...")
    create_tables()
    db = get_db_session()

    try:
        # Test new create_notification
        test_email_id = f"new_test_email_{datetime.now().timestamp()}"
        new_notification = create_notification(
            db,
            subject="New Test Maintenance Email",
            received_at=datetime.utcnow(),
            original_email_id_str=test_email_id,
            sender="test-sender@example.com",
            email_body_text="This is a test for the new notification structure.",
        )
        assert new_notification is not None
        assert new_notification.raw_email_data is not None
        assert new_notification.llm_data is not None
        logger.info(
            f"Created Notification: ID {new_notification.id}, Title: {new_notification.title}, Status: {new_notification.status.value}"
        )
        logger.info(
            f"  RawEmail ID: {new_notification.raw_email_id}, Subject: {new_notification.raw_email_data.subject}"
        )
        logger.info(
            f"  LLMData ID: {new_notification.llm_data_id}, Status: {new_notification.llm_data.processing_status.value}"
        )

        # Test get_notification_by_original_email_id
        retrieved_notification = get_notification_by_original_email_id(
            db, test_email_id
        )
        assert retrieved_notification is not None
        assert retrieved_notification.id == new_notification.id
        logger.info(
            f"Retrieved notification by original email ID ({test_email_id}): ID {retrieved_notification.id}"
        )

        if new_notification and new_notification.llm_data:
            llm_data_id_to_update = new_notification.llm_data.id
            # Test update_llm_data_extracted_fields
            updated_llm_data = update_llm_data_extracted_fields(
                db,
                llm_data_id=llm_data_id_to_update,
                extracted_service_name="TestService",
                event_start_time=datetime.utcnow(),
                event_end_time=datetime.utcnow(),
                notification_type=NotificationTypeEnum.MAINTENANCE,
                severity=SeverityEnum.LOW,
                llm_summary="LLM summary of maintenance.",
                raw_llm_response='{"key": "value"}',
                processing_status=ProcessingStatusEnum.COMPLETED,
            )
            assert updated_llm_data is not None
            assert updated_llm_data.processing_status == ProcessingStatusEnum.COMPLETED
            db.refresh(new_notification)  # Refresh to get updated notification status
            assert new_notification.status == NotificationStatusEnum.TRIAGED
            logger.info(
                f"Updated LLMData ID {llm_data_id_to_update} with extracted fields. Notification status: {new_notification.status.value}"
            )

            # Test update_llm_data_status (e.g., an error occurs)
            error_updated_llm_data = update_llm_data_status(
                db,
                llm_data_id=llm_data_id_to_update,
                processing_status=ProcessingStatusEnum.ERROR,
                error_message="Simulated LLM processing error",
            )
            assert error_updated_llm_data is not None
            assert (
                error_updated_llm_data.processing_status == ProcessingStatusEnum.ERROR
            )
            db.refresh(new_notification)  # Refresh to get updated notification status
            assert new_notification.status == NotificationStatusEnum.ERROR_PROCESSING
            logger.info(
                f"Updated LLMData ID {llm_data_id_to_update} status to ERROR. Notification status: {new_notification.status.value}"
            )

        # Test get_notifications
        notifications_list = get_notifications(
            db,
            limit=5,
            options=[
                joinedload(Notification.raw_email_data),
                joinedload(Notification.llm_data),
            ],
        )
        logger.info(
            f"Retrieved {len(notifications_list)} notifications via get_notifications:"
        )
        for n in notifications_list:
            logger.info(
                f"  ID: {n.id}, Title: {n.title}, RawEmail Subject: {n.raw_email_data.subject if n.raw_email_data else 'N/A'}, LLM Status: {n.llm_data.processing_status.value if n.llm_data else 'N/A'}"
            )

        # Test get_pending_notifications
        # First, create one that should be pending
        pending_email_id = f"pending_email_{datetime.now().timestamp()}"
        pending_notification = create_notification(
            db,
            subject="Pending Email Test",
            received_at=datetime.utcnow(),
            original_email_id_str=pending_email_id,
        )
        if pending_notification:
            logger.info(
                f"Created another notification ID {pending_notification.id} that should be pending initially."
            )

        pending_list = get_pending_notifications(db, limit=5)
        logger.info(f"Retrieved {len(pending_list)} PENDING notifications:")
        for p_n in pending_list:
            logger.info(
                f"  Pending ID: {p_n.id}, LLMData Status: {p_n.llm_data.processing_status.value if p_n.llm_data else 'N/A'}"
            )
            assert p_n.llm_data.processing_status == ProcessingStatusEnum.UNPROCESSED

        db.commit()  # Commit all test changes
    except Exception as e:
        logger.error(f"Error during CRUD operations test: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
    logger.info("CRUD operations test finished.")
