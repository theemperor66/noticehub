import pytest
from sqlalchemy.orm import Session
from typing import List

from src.data import crud
from src.data.models import InternalSystem, ExternalService, Dependency
# Schemas are not directly used by CRUD functions in these tests
# from src.data.schemas import InternalSystemCreate, InternalSystemUpdate


# Helper to create an external service, needed for testing dependency checks
def _create_external_service(
    db: Session, name: str = "Test Ext Service For IS Test"
) -> ExternalService:
    return crud.create_external_service(
        db,
        service_name=name,
        provider="Test Provider",
        description="Test desc for IS test helper",
    )


# Helper to create a dependency, needed for testing dependency checks
def _create_dependency(
    db: Session, internal_system_id: int, external_service_id: int
) -> Dependency:
    return crud.create_dependency(
        db,
        internal_system_id=internal_system_id,
        external_service_id=external_service_id,
        dependency_description="Test dep for internal system test",
    )


def test_create_internal_system(db_session: Session):
    system_name = "Test System Alpha IS"
    responsible_contact = "alpha_is@example.com"
    description = "Alpha internal system description"

    db_system = crud.create_internal_system(
        db=db_session,
        system_name=system_name,
        responsible_contact=responsible_contact,
        description=description,
    )

    assert db_system is not None
    assert db_system.system_name == system_name
    assert db_system.responsible_contact == responsible_contact
    assert db_system.description == description
    assert db_system.id is not None


def test_create_internal_system_already_exists(db_session: Session):
    system_name = "Test System Beta IS"
    crud.create_internal_system(db=db_session, system_name=system_name)
    db_system_again = crud.create_internal_system(
        db=db_session, system_name=system_name
    )
    assert db_system_again is not None
    assert db_system_again.system_name == system_name
    systems: List[InternalSystem] = (
        db_session.query(InternalSystem)
        .filter(InternalSystem.system_name == system_name)
        .all()
    )
    assert len(systems) == 1


def test_get_internal_system(db_session: Session):
    system_name_gamma = "Test System Gamma IS"
    system = crud.create_internal_system(db=db_session, system_name=system_name_gamma)
    assert system is not None
    fetched_system = crud.get_internal_system(db=db_session, system_id=system.id)
    assert fetched_system is not None
    assert fetched_system.id == system.id
    assert fetched_system.system_name == system_name_gamma


def test_get_internal_system_not_found(db_session: Session):
    fetched_system = crud.get_internal_system(db=db_session, system_id=99901)
    assert fetched_system is None


def test_get_internal_system_by_name(db_session: Session):
    system_name_delta = "Test System Delta UniqueName IS"
    crud.create_internal_system(db=db_session, system_name=system_name_delta)
    fetched_system = crud.get_internal_system_by_name(
        db=db_session, system_name=system_name_delta
    )
    assert fetched_system is not None
    assert fetched_system.system_name == system_name_delta


def test_get_internal_system_by_name_not_found(db_session: Session):
    fetched_system = crud.get_internal_system_by_name(
        db=db_session, system_name="NonExistentSystemName IS"
    )
    assert fetched_system is None


def test_get_internal_systems(db_session: Session):
    initial_systems_count = len(
        crud.get_internal_systems(db=db_session, skip=0, limit=1000)
    )
    sys1_name = "System Epsilon UniqueForGetList IS"
    sys2_name = "System Zeta UniqueForGetList IS"
    crud.create_internal_system(db=db_session, system_name=sys1_name)
    crud.create_internal_system(db=db_session, system_name=sys2_name)

    systems = crud.get_internal_systems(db=db_session, skip=0, limit=10)
    assert len(systems) == initial_systems_count + 2

    systems_limit_1 = crud.get_internal_systems(db=db_session, skip=0, limit=1)
    assert len(systems_limit_1) == 1

    all_systems_ordered = sorted(
        crud.get_internal_systems(db=db_session, skip=0, limit=1000), key=lambda x: x.id
    )
    if len(all_systems_ordered) > 1:
        systems_skip_1_limit_1 = crud.get_internal_systems(
            db=db_session, skip=1, limit=1
        )
        assert len(systems_skip_1_limit_1) == 1
        # Assuming IDs are sequential for new items or ordered by ID by default (safer to sort for test stability)
        assert systems_skip_1_limit_1[0].id == all_systems_ordered[1].id


def test_update_internal_system(db_session: Session):
    system_name_eta_orig = "System Eta Original IS"
    system = crud.create_internal_system(
        db=db_session,
        system_name=system_name_eta_orig,
        responsible_contact="old_contact_is@example.com",
    )
    assert system is not None
    update_data = {
        "system_name": "System Eta Updated IS",
        "responsible_contact": "new_contact_is@example.com",
        "description": "Eta Updated IS Description",
    }
    updated_system = crud.update_internal_system(
        db=db_session, system_id=system.id, **update_data
    )
    assert updated_system is not None
    assert updated_system.system_name == "System Eta Updated IS"
    assert updated_system.responsible_contact == "new_contact_is@example.com"
    assert updated_system.description == "Eta Updated IS Description"


def test_update_internal_system_name_conflict(db_session: Session):
    existing_name = "Existing SystemName ForConflict IS"
    crud.create_internal_system(db=db_session, system_name=existing_name)
    original_name_update = "Original SystemName ForUpdateConflict IS"
    system_to_update = crud.create_internal_system(
        db=db_session, system_name=original_name_update
    )
    updated_system = crud.update_internal_system(
        db=db_session, system_id=system_to_update.id, system_name=existing_name
    )
    assert updated_system is None


def test_update_internal_system_not_found(db_session: Session):
    updated_system = crud.update_internal_system(
        db=db_session, system_id=99902, system_name="Doesn't Matter System IS"
    )
    assert updated_system is None


def test_update_internal_system_no_changes(db_session: Session):
    system_name_theta = "System Theta UniqueNoChangeIS"
    contact_theta = "theta_contact_is@example.com"
    system = crud.create_internal_system(
        db=db_session, system_name=system_name_theta, responsible_contact=contact_theta
    )
    assert system is not None
    updated_system = crud.update_internal_system(
        db=db_session, system_id=system.id, responsible_contact=contact_theta
    )
    assert updated_system is not None
    assert updated_system.system_name == system_name_theta
    assert updated_system.responsible_contact == contact_theta
    updated_system_no_args = crud.update_internal_system(
        db=db_session, system_id=system.id
    )
    assert updated_system_no_args is not None
    assert updated_system_no_args.system_name == system_name_theta


def test_delete_internal_system(db_session: Session):
    system_name_iota = "System Iota UniqueDeleteIS"
    system = crud.create_internal_system(db=db_session, system_name=system_name_iota)
    assert system is not None
    system_id = system.id
    deleted = crud.delete_internal_system(db=db_session, system_id=system_id)
    assert deleted is True
    fetched_system = crud.get_internal_system(db=db_session, system_id=system_id)
    assert fetched_system is None


def test_delete_internal_system_not_found(db_session: Session):
    deleted = crud.delete_internal_system(db=db_session, system_id=99903)
    assert deleted is False


def test_delete_internal_system_with_dependencies(db_session: Session):
    ext_service_name = "ExtServiceForISDepTest UniqueIS"
    ext_service = _create_external_service(db_session, ext_service_name)
    assert ext_service is not None
    internal_sys_name = "InternalSystem Kappa Unique (with deps IS)"
    internal_sys = crud.create_internal_system(
        db=db_session, system_name=internal_sys_name
    )
    assert internal_sys is not None
    dependency = _create_dependency(db_session, internal_sys.id, ext_service.id)
    assert dependency is not None
    db_session.refresh(internal_sys)
    deleted = crud.delete_internal_system(db=db_session, system_id=internal_sys.id)
    assert deleted is False
    fetched_system = crud.get_internal_system(db=db_session, system_id=internal_sys.id)
    assert fetched_system is not None
