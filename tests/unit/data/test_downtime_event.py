from datetime import datetime, timedelta, timezone

import pytest

from src.data import crud
from src.data.models import SeverityEnum


def test_create_and_close_downtime_event(db_session):
    svc = crud.create_external_service(
        db_session, service_name="DowntimeSvc", provider="x"
    )
    start_notif = crud.create_notification(
        db=db_session,
        subject="start",
        received_at=datetime.now(timezone.utc),
        original_email_id_str="start1",
    )
    event = crud.create_downtime_event(
        db_session,
        external_service_id=svc.id,
        start_notification_id=start_notif.id,
        start_time=start_notif.raw_email_data.received_at,
        severity=SeverityEnum.HIGH,
    )
    assert event.id is not None
    assert event.end_time is None

    end_notif = crud.create_notification(
        db=db_session,
        subject="end",
        received_at=datetime.now(timezone.utc) + timedelta(hours=1),
        original_email_id_str="end1",
    )
    closed = crud.close_downtime_event(
        db_session, event.id, end_notif.id, end_notif.raw_email_data.received_at
    )
    assert closed.end_notification_id == end_notif.id
    assert closed.end_time == end_notif.raw_email_data.received_at
    assert closed.duration_minutes == 60


def test_get_open_downtime_event_for_service(db_session):
    svc = crud.create_external_service(
        db_session, service_name="AnotherSvc", provider="y"
    )
    start_notif = crud.create_notification(
        db=db_session,
        subject="start2",
        received_at=datetime.now(timezone.utc),
        original_email_id_str="start2",
    )
    event = crud.create_downtime_event(
        db_session,
        external_service_id=svc.id,
        start_notification_id=start_notif.id,
        start_time=start_notif.raw_email_data.received_at,
    )
    fetched = crud.get_open_downtime_event_for_service(db_session, svc.id)
    assert fetched is not None
    assert fetched.id == event.id


def test_get_downtime_events_and_stats(db_session):
    svc = crud.create_external_service(db_session, service_name="StatSvc", provider="z")
    start_time = datetime.now(timezone.utc)
    start_notif = crud.create_notification(
        db=db_session,
        subject="s",
        received_at=start_time,
        original_email_id_str="s1",
    )
    end_notif = crud.create_notification(
        db=db_session,
        subject="e",
        received_at=start_time + timedelta(minutes=30),
        original_email_id_str="e1",
    )
    event = crud.create_downtime_event(
        db_session,
        external_service_id=svc.id,
        start_notification_id=start_notif.id,
        start_time=start_time,
    )
    crud.close_downtime_event(
        db_session, event.id, end_notif.id, end_notif.raw_email_data.received_at
    )
    events = crud.get_downtime_events(db_session, external_service_id=svc.id)
    assert len(events) == 1
    stats = crud.get_average_downtime_by_service(db_session)
    stat = next((s for s in stats if s["service_id"] == svc.id), None)
    assert stat is not None
    assert round(stat["average_minutes"]) == 30
    assert stat["event_count"] == 1
