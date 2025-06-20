import os
from sqlalchemy.orm import Session
from src.data.seed_demo_data import seed_demo_data
from src.data.models import Notification, ExternalService, InternalSystem, Dependency
from src.config import PROJECT_ROOT


def test_seed_demo_data(db_session: Session):
    path = os.path.join(PROJECT_ROOT, "scripts", "demo_data.json")
    seed_demo_data(db_session, json_path=path)

    assert db_session.query(Notification).count() > 0
    assert db_session.query(ExternalService).count() > 0
    assert db_session.query(InternalSystem).count() > 0
    assert db_session.query(Dependency).count() > 0

    counts = (
        db_session.query(Notification).count(),
        db_session.query(ExternalService).count(),
        db_session.query(InternalSystem).count(),
        db_session.query(Dependency).count(),
    )
    seed_demo_data(db_session, json_path=path)
    counts_after = (
        db_session.query(Notification).count(),
        db_session.query(ExternalService).count(),
        db_session.query(InternalSystem).count(),
        db_session.query(Dependency).count(),
    )
    assert counts == counts_after

