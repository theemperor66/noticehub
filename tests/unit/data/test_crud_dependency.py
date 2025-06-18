import pytest
from sqlalchemy.orm import Session
from typing import List

from src.data import crud
from src.data.models import InternalSystem, ExternalService, Dependency

# Helper to create an internal system more directly for these tests
def _create_internal_system_for_dep_test(db: Session, name: str) -> InternalSystem:
    is_ = InternalSystem(system_name=name, responsible_contact=f"{name.replace(' ', '_')}@example.com", description=f"Desc for {name}")
    db.add(is_)
    db.commit()
    db.refresh(is_)
    return is_

# Helper to create an external service more directly for these tests
def _create_external_service_for_dep_test(db: Session, name: str) -> ExternalService:
    es_ = ExternalService(service_name=name, provider=f"{name} Provider", description=f"Desc for {name}")
    db.add(es_)
    db.commit()
    db.refresh(es_)
    return es_

@pytest.fixture
def setup_systems_for_dependency_tests(db_session: Session):
    """Fixture to pre-populate an internal system and an external service for dependency tests."""
    internal_sys = _create_internal_system_for_dep_test(db_session, "IS for Dep Tests Unique")
    external_serv = _create_external_service_for_dep_test(db_session, "ES for Dep Tests Unique")
    return internal_sys, external_serv

def test_create_dependency(db_session: Session, setup_systems_for_dependency_tests):
    internal_sys, external_serv = setup_systems_for_dependency_tests
    description = "Initial dependency description for create test"
    
    db_dependency = crud.create_dependency(
        db=db_session, 
        internal_system_id=internal_sys.id, 
        external_service_id=external_serv.id, 
        dependency_description=description
    )
    
    assert db_dependency is not None
    assert db_dependency.internal_system_id == internal_sys.id
    assert db_dependency.external_service_id == external_serv.id
    assert db_dependency.dependency_description == description
    assert db_dependency.id is not None
    # Eager loading checks (assuming create_dependency also eager loads or get_dependency is called indirectly)
    # To be more direct, one might call get_dependency(db_dependency.id) here.
    # For now, assume create_dependency returns the object with relationships if possible.
    retrieved_dep = crud.get_dependency(db_session, db_dependency.id)
    assert retrieved_dep.internal_system.system_name == internal_sys.system_name 
    assert retrieved_dep.external_service.service_name == external_serv.service_name

def test_create_dependency_already_exists(db_session: Session, setup_systems_for_dependency_tests):
    internal_sys, external_serv = setup_systems_for_dependency_tests
    crud.create_dependency(db_session, internal_sys.id, external_serv.id, "First time dep exists")
    db_dependency_again = crud.create_dependency(db_session, internal_sys.id, external_serv.id, "Second attempt dep exists")
    
    assert db_dependency_again is not None
    assert db_dependency_again.dependency_description == "First time dep exists" # CRUD returns existing
    
    dependencies: List[Dependency] = db_session.query(Dependency).filter_by(
        internal_system_id=internal_sys.id, 
        external_service_id=external_serv.id
    ).all()
    assert len(dependencies) == 1

def test_create_dependency_missing_internal_system(db_session: Session, setup_systems_for_dependency_tests):
    _, external_serv = setup_systems_for_dependency_tests
    db_dependency = crud.create_dependency(db_session, 99904, external_serv.id, "Missing IS for dep")
    assert db_dependency is None

def test_create_dependency_missing_external_service(db_session: Session, setup_systems_for_dependency_tests):
    internal_sys, _ = setup_systems_for_dependency_tests
    db_dependency = crud.create_dependency(db_session, internal_sys.id, 99905, "Missing ES for dep")
    assert db_dependency is None

def test_get_dependency(db_session: Session, setup_systems_for_dependency_tests):
    internal_sys, external_serv = setup_systems_for_dependency_tests
    dep = crud.create_dependency(db_session, internal_sys.id, external_serv.id, "Dep for Get Test Unique")
    assert dep is not None

    fetched_dep = crud.get_dependency(db=db_session, dependency_id=dep.id)
    assert fetched_dep is not None
    assert fetched_dep.id == dep.id
    assert fetched_dep.internal_system is not None
    assert fetched_dep.external_service is not None

def test_get_dependency_not_found(db_session: Session):
    fetched_dep = crud.get_dependency(db=db_session, dependency_id=99906)
    assert fetched_dep is None

def test_get_dependencies(db_session: Session, setup_systems_for_dependency_tests):
    initial_deps_count = len(crud.get_dependencies(db_session, limit=1000))
    is1, es1 = setup_systems_for_dependency_tests # This fixture creates one pair

    # Create another distinct pair for this test
    is2 = _create_internal_system_for_dep_test(db_session, "IS2 for DepList Test")
    es2 = _create_external_service_for_dep_test(db_session, "ES2 for DepList Test")

    # Dep1 from fixture setup (if create_dependency was called in fixture or implicitly by other tests using it)
    # Let's ensure specific deps for this test count
    crud.create_dependency(db_session, is1.id, es1.id, "Dep 1 Unique for GetList") # This might be a re-creation, handled by create_dependency
    dep2 = crud.create_dependency(db_session, is2.id, es2.id, "Dep 2 Unique for GetList") 

    # Recalculate count based on how many unique dependencies were actually added
    # If create_dependency returns existing, the count logic must be careful
    # Count after additions
    current_deps = crud.get_dependencies(db=db_session, skip=0, limit=1000)
    expected_new_deps = 1 if db_session.query(Dependency).filter_by(internal_system_id=is1.id, external_service_id=es1.id).count() > 0 else 0
    expected_new_deps += 1 # for dep2
    # This is tricky because the fixture `setup_systems_for_dependency_tests` is function-scoped, so IS/ES are new each time.
    # And create_dependency handles existing. A simpler count may be needed for this test if we are sure of isolation.
    # Let's assume we added 2 distinct dependencies or that create_dependency handles re-creation gracefully for counting.
    
    # Clean approach: count before, add N, count after, assert diff is N.
    count_before = len(crud.get_dependencies(db_session, limit=2000)) # get all deps before adding new ones for this test
    _is_t1 = _create_internal_system_for_dep_test(db_session, "IS_T1_get_deps")
    _es_t1 = _create_external_service_for_dep_test(db_session, "ES_T1_get_deps")
    _is_t2 = _create_internal_system_for_dep_test(db_session, "IS_T2_get_deps")
    _es_t2 = _create_external_service_for_dep_test(db_session, "ES_T2_get_deps")
    crud.create_dependency(db_session, _is_t1.id, _es_t1.id, "TDep1")
    crud.create_dependency(db_session, _is_t2.id, _es_t2.id, "TDep2")
    count_after = len(crud.get_dependencies(db_session, limit=2000))
    assert count_after == count_before + 2

    dependencies_limit_1 = crud.get_dependencies(db=db_session, skip=0, limit=1)
    assert len(dependencies_limit_1) >= 1 if count_after > 0 else 0 # check if any exist
    
    all_deps_ordered = sorted(crud.get_dependencies(db_session, limit=1000), key=lambda x: x.id)
    if len(all_deps_ordered) > 1:
        dependencies_skip_1 = crud.get_dependencies(db=db_session, skip=1, limit=1)
        assert len(dependencies_skip_1) == 1
        assert dependencies_skip_1[0].id == all_deps_ordered[1].id

def test_get_dependencies_for_internal_system(db_session: Session, setup_systems_for_dependency_tests):
    is1, es1 = setup_systems_for_dependency_tests
    is2 = _create_internal_system_for_dep_test(db_session, "IS2 for DepFilter Unique")
    es2 = _create_external_service_for_dep_test(db_session, "ES2 for DepFilter Unique")

    crud.create_dependency(db_session, is1.id, es1.id, "IS1-ES1 dep filter")
    crud.create_dependency(db_session, is1.id, es2.id, "IS1-ES2 dep filter") 
    crud.create_dependency(db_session, is2.id, es1.id, "IS2-ES1 dep filter")
    
    is1_deps = crud.get_dependencies_for_internal_system(db_session, is1.id, limit=10)
    assert len(is1_deps) == 2
    non_existent_is_deps = crud.get_dependencies_for_internal_system(db_session, 99907)
    assert len(non_existent_is_deps) == 0

def test_get_dependencies_for_external_service(db_session: Session, setup_systems_for_dependency_tests):
    is1, es1 = setup_systems_for_dependency_tests
    is2 = _create_internal_system_for_dep_test(db_session, "IS2 for ESFilter Unique")
    es2 = _create_external_service_for_dep_test(db_session, "ES2 for ESFilter Unique")

    crud.create_dependency(db_session, is1.id, es1.id, "IS1-ES1 es_filter")
    crud.create_dependency(db_session, is2.id, es1.id, "IS2-ES1 es_filter") 
    crud.create_dependency(db_session, is1.id, es2.id, "IS1-ES2 es_filter")

    es1_deps = crud.get_dependencies_for_external_service(db_session, es1.id, limit=10)
    assert len(es1_deps) == 2
    non_existent_es_deps = crud.get_dependencies_for_external_service(db_session, 99908)
    assert len(non_existent_es_deps) == 0

def test_update_dependency(db_session: Session, setup_systems_for_dependency_tests):
    internal_sys, external_serv = setup_systems_for_dependency_tests
    dep = crud.create_dependency(db_session, internal_sys.id, external_serv.id, "Old Description for update test")
    assert dep is not None
    new_description = "New Updated Description for update test"
    updated_dep = crud.update_dependency(db=db_session, dependency_id=dep.id, dependency_description=new_description)
    assert updated_dep is not None
    assert updated_dep.dependency_description == new_description

def test_update_dependency_no_change(db_session: Session, setup_systems_for_dependency_tests):
    internal_sys, external_serv = setup_systems_for_dependency_tests
    original_description = "Original Desc No Change dep test"
    dep = crud.create_dependency(db_session, internal_sys.id, external_serv.id, original_description)
    updated_dep = crud.update_dependency(db_session, dep.id, original_description)
    assert updated_dep.dependency_description == original_description
    updated_dep_none = crud.update_dependency(db_session, dep.id, None)
    assert updated_dep_none.dependency_description == original_description

def test_update_dependency_not_found(db_session: Session):
    updated_dep = crud.update_dependency(db=db_session, dependency_id=99909, dependency_description="Doesn't Matter dep test")
    assert updated_dep is None

def test_delete_dependency(db_session: Session, setup_systems_for_dependency_tests):
    internal_sys, external_serv = setup_systems_for_dependency_tests
    dep = crud.create_dependency(db_session, internal_sys.id, external_serv.id, "Dep to Delete Unique")
    assert dep is not None
    dep_id = dep.id
    deleted = crud.delete_dependency(db=db_session, dependency_id=dep_id)
    assert deleted is True
    fetched_dep = crud.get_dependency(db=db_session, dependency_id=dep_id)
    assert fetched_dep is None

def test_delete_dependency_not_found(db_session: Session):
    deleted = crud.delete_dependency(db=db_session, dependency_id=99910)
    assert deleted is False
