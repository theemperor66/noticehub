import pytest
from sqlalchemy.orm import Session
from typing import List

from src.data import crud
from src.data.models import ExternalService, InternalSystem, Dependency
from src.data.schemas import ExternalServiceCreate, ExternalServiceUpdate


# Helper to create an internal system, needed for testing dependency checks
def _create_internal_system(db: Session, name: str = "Test System") -> InternalSystem:
    # This uses the actual CRUD function for InternalSystem. Ensure it's robust.
    # For pure unit tests of ExternalService, one might mock this or insert directly.
    # However, given the context of achieving coverage, using the available CRUD is practical.
    return crud.create_internal_system(
        db,
        system_name=name,
        responsible_contact="test_contact@example.com",
        description="A test internal system",
    )


# Helper to create a dependency, needed for testing dependency checks
def _create_dependency(
    db: Session, internal_system_id: int, external_service_id: int
) -> Dependency:
    return crud.create_dependency(
        db,
        internal_system_id=internal_system_id,
        external_service_id=external_service_id,
        dependency_description="A test dependency",
    )


def test_create_external_service(db_session: Session):
    service_name = "Test Service Alpha"
    provider = "Test Provider"
    description = "Test Description"

    # service_in = ExternalServiceCreate(service_name=service_name, provider=provider, description=description)
    # db_service = crud.create_external_service(db=db_session, service_name=service_in.service_name, provider=service_in.provider, description=service_in.description)
    db_service = crud.create_external_service(
        db=db_session,
        service_name=service_name,
        provider=provider,
        description=description,
    )

    assert db_service is not None
    assert db_service.service_name == service_name
    assert db_service.provider == provider
    assert db_service.description == description
    assert db_service.id is not None


def test_create_external_service_already_exists(db_session: Session):
    service_name = "Test Service Beta"
    crud.create_external_service(
        db=db_session, service_name=service_name
    )  # Create first time

    # Attempt to create again
    db_service_again = crud.create_external_service(
        db=db_session, service_name=service_name
    )

    assert db_service_again is not None
    assert db_service_again.service_name == service_name

    services: List[ExternalService] = (
        db_session.query(ExternalService)
        .filter(ExternalService.service_name == service_name)
        .all()
    )
    assert (
        len(services) == 1
    )  # create_external_service should return existing if name matches


def test_get_external_service(db_session: Session):
    service = crud.create_external_service(
        db=db_session, service_name="Test Service Gamma"
    )
    assert service is not None

    fetched_service = crud.get_external_service(db=db_session, service_id=service.id)
    assert fetched_service is not None
    assert fetched_service.id == service.id
    assert fetched_service.service_name == "Test Service Gamma"


def test_get_external_service_not_found(db_session: Session):
    fetched_service = crud.get_external_service(db=db_session, service_id=99999)
    assert fetched_service is None


def test_get_external_service_by_name(db_session: Session):
    service_name = "Test Service Delta"
    crud.create_external_service(db=db_session, service_name=service_name)

    fetched_service = crud.get_external_service_by_name(
        db=db_session, service_name=service_name
    )
    assert fetched_service is not None
    assert fetched_service.service_name == service_name


def test_get_external_service_by_name_not_found(db_session: Session):
    fetched_service = crud.get_external_service_by_name(
        db=db_session, service_name="NonExistentService"
    )
    assert fetched_service is None


def test_get_external_services(db_session: Session):
    # Clean slate for this specific test if possible, or account for existing items
    initial_services = crud.get_external_services(db=db_session, skip=0, limit=1000)
    initial_count = len(initial_services)

    s1 = crud.create_external_service(
        db=db_session, service_name="Service Epsilon Unique"
    )
    s2 = crud.create_external_service(db=db_session, service_name="Service Zeta Unique")

    services = crud.get_external_services(db=db_session, skip=0, limit=10)
    # Check count based on what was added in this test + initial_count
    assert len(services) == initial_count + 2

    services_limit_1 = crud.get_external_services(db=db_session, skip=0, limit=1)
    assert len(services_limit_1) == 1

    # Ensure skip works. Get all, then skip 1 and check if the second item is what we expect.
    all_services_ordered = sorted(
        crud.get_external_services(db=db_session, skip=0, limit=1000),
        key=lambda x: x.id,
    )
    if len(all_services_ordered) > 1:
        services_skip_1_limit_1 = crud.get_external_services(
            db=db_session, skip=1, limit=1
        )
        assert len(services_skip_1_limit_1) == 1
        # This assertion depends on the default ordering of get_external_services or assumes IDs are sequential for new items
        # It's safer to sort by ID for comparison if default order isn't guaranteed
        sorted_services = sorted(services, key=lambda x: x.id)
        if len(sorted_services) > 1:
            assert services_skip_1_limit_1[0].id == sorted_services[1].id


def test_update_external_service(db_session: Session):
    service = crud.create_external_service(
        db=db_session, service_name="Service Eta", provider="OldProvider"
    )
    assert service is not None

    update_data = {
        "service_name": "Service Eta Updated",
        "provider": "NewProvider",
        "description": "Updated Description",
    }
    updated_service = crud.update_external_service(
        db=db_session, service_id=service.id, **update_data
    )

    assert updated_service is not None
    assert updated_service.service_name == "Service Eta Updated"
    assert updated_service.provider == "NewProvider"
    assert updated_service.description == "Updated Description"


def test_update_external_service_name_conflict(db_session: Session):
    crud.create_external_service(
        db=db_session, service_name="Existing Name ForConflictTest"
    )
    service_to_update = crud.create_external_service(
        db=db_session, service_name="Original Name ForConflictTest"
    )

    updated_service = crud.update_external_service(
        db=db_session,
        service_id=service_to_update.id,
        service_name="Existing Name ForConflictTest",
    )
    assert updated_service is None  # Should fail due to name conflict


def test_update_external_service_not_found(db_session: Session):
    updated_service = crud.update_external_service(
        db=db_session, service_id=88888, service_name="Doesn't Matter"
    )
    assert updated_service is None


def test_update_external_service_no_changes(db_session: Session):
    service_name_theta = "Service Theta UniqueNoChange"
    provider_theta = "Provider Theta"
    service = crud.create_external_service(
        db=db_session, service_name=service_name_theta, provider=provider_theta
    )
    assert service is not None

    # Try to update with the same data or no data
    updated_service = crud.update_external_service(
        db=db_session, service_id=service.id, provider=provider_theta
    )
    assert updated_service is not None
    # Check that the service_name (which wasn't part of update args) is still the same
    assert updated_service.service_name == service_name_theta
    assert updated_service.provider == provider_theta

    updated_service_no_args = crud.update_external_service(
        db=db_session, service_id=service.id
    )
    assert updated_service_no_args is not None
    assert updated_service_no_args.service_name == service_name_theta


def test_delete_external_service(db_session: Session):
    service_name_iota = "Service Iota UniqueDelete"
    service = crud.create_external_service(
        db=db_session, service_name=service_name_iota
    )
    assert service is not None
    service_id = service.id

    deleted = crud.delete_external_service(db=db_session, service_id=service_id)
    assert deleted is True

    fetched_service = crud.get_external_service(db=db_session, service_id=service_id)
    assert fetched_service is None


def test_delete_external_service_not_found(db_session: Session):
    deleted = crud.delete_external_service(db=db_session, service_id=77777)
    assert deleted is False


def test_delete_external_service_with_dependencies(db_session: Session):
    # 1. Create an internal system
    internal_sys_name = "SysForDepTest Unique"
    internal_sys = _create_internal_system(db_session, internal_sys_name)
    assert internal_sys is not None

    # 2. Create an external service
    ext_service_name = "Service Kappa Unique (with deps)"
    ext_service = crud.create_external_service(
        db=db_session, service_name=ext_service_name
    )
    assert ext_service is not None

    # 3. Create a dependency
    dependency = _create_dependency(db_session, internal_sys.id, ext_service.id)
    assert dependency is not None
    db_session.refresh(
        ext_service
    )  # Refresh to load the 'dependencies' relationship if needed by CRUD

    # 4. Attempt to delete the external service
    deleted = crud.delete_external_service(db=db_session, service_id=ext_service.id)
    assert deleted is False  # Should fail because of the dependency

    # 5. Verify the service still exists
    fetched_service = crud.get_external_service(
        db=db_session, service_id=ext_service.id
    )
    assert fetched_service is not None
