from datetime import datetime, timezone

from src.data import crud
from src.data.models import NotificationTypeEnum, SeverityEnum, ProcessingStatusEnum


def test_analyze_notification_impacts(db_session):
    isys = crud.create_internal_system(db_session, "IS1", "owner@example.com", "desc")
    es = crud.create_external_service(db_session, "ServiceX", "Provider", "desc")
    crud.create_dependency(db_session, isys.id, es.id)

    notif = crud.create_notification(
        db=db_session,
        subject="Test",
        received_at=datetime.now(timezone.utc),
        original_email_id_str="uid123",
    )

    crud.update_llm_data_extracted_fields(
        db_session,
        notif.llm_data.id,
        extracted_service_name=es.service_name,
        event_start_time=None,
        event_end_time=None,
        notification_type=NotificationTypeEnum.MAINTENANCE,
        severity=SeverityEnum.LOW,
        llm_summary="sum",
        raw_llm_response="{}",
        processing_status=ProcessingStatusEnum.COMPLETED,
    )

    impacts = crud.analyze_notification_impacts(db_session, notif.id, es.service_name)
    assert len(impacts) == 1
    assert impacts[0].internal_system_id == isys.id
