import pytest
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import hashlib

from src.data import crud
from src.data.models import (
    Notification,
    ExternalService,
    InternalSystem,
    NotificationStatusEnum,  # Removed NotificationSourceType, NotificationPriority
    ProcessingStatusEnum,
    RawEmail,
    LLMData,
    NotificationTypeEnum,
    SeverityEnum,  # Added Enums
)


# Helper to create an external service. Ensures uniqueness for test runs.
def _ensure_external_service(
    db: Session, name: str = "Test SP for Notif CRUD"
) -> ExternalService:
    existing = crud.get_external_service_by_name(db, name)
    if existing:
        return existing
    return crud.create_external_service(
        db,
        service_name=name,
        provider="Test Provider Co",
        description="Acts as a service provider for notifications",
    )


# Helper to create an internal system. Ensures uniqueness for test runs.
def _ensure_internal_system(
    db: Session, name: str = "Test IS for Notif Link CRUD"
) -> InternalSystem:
    existing = crud.get_internal_system_by_name(db, name)
    if existing:
        return existing
    return crud.create_internal_system(
        db,
        system_name=name,
        responsible_contact=f"{name.replace(' ', '_')}@example.com",
        description="IS for notification link testing",
    )


@pytest.fixture
def basic_notification_from_email_factory(db_session: Session):
    """
    Factory to create a basic notification using crud.create_notification,
    simulating an incoming email.
    """

    def _factory(suffix: str = ""):
        timestamp_suffix = str(datetime.now().timestamp()).replace(
            ".", ""
        )  # Ensure unique email ID
        original_email_id = f"test_email_id_{suffix}{timestamp_suffix}"
        subject = f"Test Email Subject {suffix}"
        received = datetime.now(timezone.utc) - timedelta(days=1)
        sender_email = f"sender{suffix}@example.com"
        body = f"This is a test email body {suffix}."

        notification = crud.create_notification(
            db=db_session,
            subject=subject,
            received_at=received,
            original_email_id_str=original_email_id,
            sender=sender_email,
            email_body_text=body,
        )
        assert notification is not None, "crud.create_notification returned None"
        assert notification.raw_email_data is not None, "RawEmail not created or linked"
        assert notification.llm_data is not None, "LLMData not created or linked"
        return notification

    return _factory


def test_create_notification_from_email(
    db_session: Session, basic_notification_from_email_factory
):
    suffix = "_create"
    subject = f"Test Email Subject {suffix}"
    original_email_id = (
        f"test_email_id_{suffix}{str(datetime.now().timestamp()).replace('.', '')}"
    )
    received_at = datetime.now(timezone.utc) - timedelta(hours=5)
    sender = f"creator{suffix}@example.com"

    db_notification = crud.create_notification(
        db=db_session,
        subject=subject,
        received_at=received_at,
        original_email_id_str=original_email_id,
        sender=sender,
        email_body_text="Email body for create test.",
    )

    assert db_notification is not None
    assert db_notification.id is not None
    assert db_notification.title == subject  # Initial title from subject
    assert db_notification.status == NotificationStatusEnum.NEW  # Initial status

    assert db_notification.raw_email_id is not None
    assert db_notification.raw_email_data is not None
    assert db_notification.raw_email_data.subject == subject
    expected_hash = hashlib.sha256(original_email_id.encode()).hexdigest()
    assert db_notification.raw_email_data.original_email_id_hash == expected_hash

    assert db_notification.llm_data_id is not None
    assert db_notification.llm_data is not None
    assert (
        db_notification.llm_data.processing_status == ProcessingStatusEnum.UNPROCESSED
    )

    # Fields on LLMData that are typically set by LLM or later updates
    assert db_notification.llm_data.extracted_service_name is None
    assert db_notification.llm_data.llm_summary is None
    assert (
        db_notification.llm_data.notification_type == NotificationTypeEnum.UNKNOWN
    )  # Default value
    assert db_notification.llm_data.severity == SeverityEnum.UNKNOWN  # Default value
    assert db_notification.llm_data.event_start_time is None
    assert db_notification.llm_data.event_end_time is None


def test_get_notification(db_session: Session, basic_notification_from_email_factory):
    created_notif = basic_notification_from_email_factory("_get")

    fetched_notif = crud.get_notification(
        db=db_session, notification_id=created_notif.id
    )
    assert fetched_notif is not None
    assert fetched_notif.id == created_notif.id
    assert fetched_notif.title == created_notif.title
    assert fetched_notif.raw_email_data is not None
    assert fetched_notif.llm_data is not None


def test_get_notification_not_found(db_session: Session):
    fetched_notif = crud.get_notification(db=db_session, notification_id=999901)
    assert fetched_notif is None


def test_get_notifications(db_session: Session, basic_notification_from_email_factory):
    all_notifications_before_test = crud.get_notifications(db_session, limit=2000)
    initial_count = len(all_notifications_before_test)

    # Create two new, unique notifications for this test
    notif1 = basic_notification_from_email_factory("_list1")
    notif2 = basic_notification_from_email_factory("_list2")

    notifications_page = crud.get_notifications(
        db=db_session, skip=0, limit=initial_count + 10
    )  # Get all, with some buffer
    assert len(notifications_page) == initial_count + 2

    # Test limit
    notifications_limit_1 = crud.get_notifications(db=db_session, skip=0, limit=1)
    assert len(notifications_limit_1) == (1 if initial_count + 2 > 0 else 0)

    # Test skip and limit combination
    # Fetch all current notifications and sort them by created_at to have a predictable order for pagination checks
    all_current_notifs_sorted_by_creation = sorted(
        crud.get_notifications(db_session, limit=2000),
        key=lambda x: x.created_at,
        reverse=True,
    )

    if len(all_current_notifs_sorted_by_creation) > 1:
        # Get the second notification from the globally sorted list
        second_item_via_skip = crud.get_notifications(db=db_session, skip=1, limit=1)
        assert len(second_item_via_skip) == 1
        assert second_item_via_skip[0].id == all_current_notifs_sorted_by_creation[1].id


def test_get_notification_by_original_email_id(db_session: Session):
    timestamp_suffix = str(datetime.now().timestamp()).replace(".", "")
    unique_email_id = f"unique_email_for_get_by_id_test_{timestamp_suffix}"

    created_notif = crud.create_notification(
        db=db_session,
        subject="Subject for get_by_original_email_id",
        received_at=datetime.now(timezone.utc),
        original_email_id_str=unique_email_id,
    )
    assert created_notif is not None

    fetched_notif = crud.get_notification_by_original_email_id(
        db_session, unique_email_id
    )
    assert fetched_notif is not None
    assert fetched_notif.id == created_notif.id
    assert (
        fetched_notif.raw_email_data.original_email_id_hash
        == hashlib.sha256(unique_email_id.encode()).hexdigest()
    )


def test_get_notification_by_original_email_id_not_found(db_session: Session):
    fetched_notif = crud.get_notification_by_original_email_id(
        db_session, "non_existent_email_id_12345"
    )
    assert fetched_notif is None


# Tests for get_pending_notifications, update_llm_data_extracted_fields, update_llm_data_status
# and potentially a new direct update_notification and delete_notification will follow.


def test_update_llm_data_extracted_fields_success(
    db_session: Session, basic_notification_from_email_factory
):
    notification = basic_notification_from_email_factory("_update_llm_fields")
    assert notification.llm_data is not None
    llm_data_id = notification.llm_data.id

    extracted_service = "AWS Maintenance"
    start_time = datetime.now(timezone.utc) + timedelta(days=1)
    end_time = start_time + timedelta(hours=2)
    notif_type = NotificationTypeEnum.MAINTENANCE
    severity_val = SeverityEnum.HIGH
    summary = "Scheduled maintenance for AWS EC2 instances."
    raw_response = '{"detail": "Full LLM response here"}'

    updated_llm_data = crud.update_llm_data_extracted_fields(
        db=db_session,
        llm_data_id=llm_data_id,
        extracted_service_name=extracted_service,
        event_start_time=start_time,
        event_end_time=end_time,
        notification_type=notif_type,
        severity=severity_val,
        llm_summary=summary,
        raw_llm_response=raw_response,
        processing_status=ProcessingStatusEnum.COMPLETED,
    )

    assert updated_llm_data is not None
    assert updated_llm_data.id == llm_data_id
    assert updated_llm_data.extracted_service_name == extracted_service
    assert (
        updated_llm_data.event_start_time.year == start_time.year
    )  # Approximate datetime check
    assert (
        updated_llm_data.event_end_time.year == end_time.year
    )  # Approximate datetime check
    assert updated_llm_data.notification_type == notif_type
    assert updated_llm_data.severity == severity_val
    assert updated_llm_data.llm_summary == summary
    assert updated_llm_data.raw_llm_response == raw_response
    assert updated_llm_data.processing_status == ProcessingStatusEnum.COMPLETED
    assert updated_llm_data.error_message is None  # Should be cleared

    # Verify parent Notification status is updated
    db_session.refresh(notification)  # Refresh to get changes from the LLM update
    assert (
        notification.status == NotificationStatusEnum.TRIAGED
    )  # Mapped from COMPLETED


def test_update_llm_data_extracted_fields_llm_data_not_found(db_session: Session):
    updated_llm_data = crud.update_llm_data_extracted_fields(
        db=db_session,
        llm_data_id=999902,  # Non-existent ID
        extracted_service_name="NonExistent",
        event_start_time=None,
        event_end_time=None,
        notification_type=NotificationTypeEnum.ALERT,
        severity=SeverityEnum.CRITICAL,
        llm_summary="N/A",
        raw_llm_response="{}",
        processing_status=ProcessingStatusEnum.COMPLETED,
    )
    assert updated_llm_data is None


def test_update_llm_data_status_to_error(
    db_session: Session, basic_notification_from_email_factory
):
    notification = basic_notification_from_email_factory("_update_llm_status_err")
    assert notification.llm_data is not None
    llm_data_id = notification.llm_data.id
    error_msg = "LLM processing failed due to API timeout."
    raw_resp_on_error = '{"error_code": 500, "message": "Timeout"}'

    updated_llm_data = crud.update_llm_data_status(
        db=db_session,
        llm_data_id=llm_data_id,
        processing_status=ProcessingStatusEnum.ERROR,
        error_message=error_msg,
        raw_llm_response=raw_resp_on_error,
    )

    assert updated_llm_data is not None
    assert updated_llm_data.id == llm_data_id
    assert updated_llm_data.processing_status == ProcessingStatusEnum.ERROR
    assert updated_llm_data.error_message == error_msg
    assert updated_llm_data.raw_llm_response == raw_resp_on_error

    # Verify parent Notification status is updated
    db_session.refresh(notification)
    assert (
        notification.status == NotificationStatusEnum.ERROR_PROCESSING
    )  # Mapped from ERROR


def test_update_llm_data_status_to_manual_review(
    db_session: Session, basic_notification_from_email_factory
):
    notification = basic_notification_from_email_factory("_update_llm_status_manual")
    assert notification.llm_data is not None
    llm_data_id = notification.llm_data.id

    updated_llm_data = crud.update_llm_data_status(
        db=db_session,
        llm_data_id=llm_data_id,
        processing_status=ProcessingStatusEnum.MANUAL_REVIEW,
    )
    assert updated_llm_data is not None
    assert updated_llm_data.processing_status == ProcessingStatusEnum.MANUAL_REVIEW
    db_session.refresh(notification)
    assert notification.status == NotificationStatusEnum.PENDING_MANUAL_REVIEW


def test_update_llm_data_status_to_pending_validation(
    db_session: Session, basic_notification_from_email_factory
):
    """Tests updating LLMData status to PENDING_VALIDATION and checks notification status mapping."""
    notification = basic_notification_from_email_factory(
        "_update_llm_status_pending_val"
    )
    assert notification.llm_data is not None
    llm_data_id = notification.llm_data.id

    updated_llm_data = crud.update_llm_data_status(
        db=db_session,
        llm_data_id=llm_data_id,
        processing_status=ProcessingStatusEnum.PENDING_VALIDATION,
    )

    assert updated_llm_data is not None
    assert updated_llm_data.id == llm_data_id
    assert updated_llm_data.processing_status == ProcessingStatusEnum.PENDING_VALIDATION

    # Verify parent Notification status is updated correctly
    db_session.refresh(notification)
    assert (
        notification.status == NotificationStatusEnum.PENDING_VALIDATION
    )  # Mapped from PENDING_VALIDATION


def test_update_llm_data_status_llm_data_not_found(db_session: Session):
    updated_llm_data = crud.update_llm_data_status(
        db=db_session,
        llm_data_id=999903,  # Non-existent ID
        processing_status=ProcessingStatusEnum.COMPLETED,
    )
    assert updated_llm_data is None


def test_get_pending_notifications(
    db_session: Session, basic_notification_from_email_factory
):
    # Ensure some notifications are definitely not pending
    done_notif = basic_notification_from_email_factory("_pending_test_done")
    assert done_notif.llm_data is not None
    crud.update_llm_data_extracted_fields(
        db_session,
        done_notif.llm_data.id,
        "Some Service",
        None,
        None,
        NotificationTypeEnum.INFO,
        SeverityEnum.LOW,
        "Summary",
        "{}",
        ProcessingStatusEnum.COMPLETED,
    )
    db_session.refresh(done_notif)
    assert done_notif.status == NotificationStatusEnum.TRIAGED  # Should not be pending

    # Create fresh notifications which should be UNPROCESSED initially
    pending_notif1 = basic_notification_from_email_factory("_pending_test1")
    pending_notif2 = basic_notification_from_email_factory("_pending_test2")

    # One set to PENDING_VALIDATION
    validation_notif = basic_notification_from_email_factory("_pending_test_valid")
    assert validation_notif.llm_data is not None
    crud.update_llm_data_status(
        db_session,
        validation_notif.llm_data.id,
        ProcessingStatusEnum.PENDING_VALIDATION,
    )

    pending_notifications = crud.get_pending_notifications(db=db_session, limit=10)

    pending_ids = {n.id for n in pending_notifications}

    assert pending_notif1.id in pending_ids
    assert pending_notif2.id in pending_ids
    assert validation_notif.id in pending_ids  # PENDING_VALIDATION should be caught
    assert done_notif.id not in pending_ids  # COMPLETED should not be caught

    for p_notif in pending_notifications:
        assert p_notif.llm_data is not None
        assert p_notif.llm_data.processing_status in [
            ProcessingStatusEnum.UNPROCESSED,
            ProcessingStatusEnum.PENDING_VALIDATION,
        ]


def test_delete_notification(db_session: Session, basic_notification_from_email_factory):
    notification = basic_notification_from_email_factory("_delete")
    notif_id = notification.id

    deleted = crud.delete_notification(db_session, notif_id)
    assert deleted is True

    fetched = crud.get_notification(db_session, notification_id=notif_id)
    assert fetched is None

    raw = db_session.query(RawEmail).filter(RawEmail.id == notification.raw_email_id).first()
    assert raw is None


def test_delete_notification_not_found(db_session: Session):
    deleted = crud.delete_notification(db_session, 999999)
    assert deleted is False
