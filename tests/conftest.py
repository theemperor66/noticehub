import sys
import os

# Add the project root directory (parent of 'src' and 'tests') to sys.path
# This allows imports like 'from src.data.models import Base'
# __file__ is tests/conftest.py
# os.path.dirname(__file__) is tests/
# os.path.join(os.path.dirname(__file__), '..') is ./
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession
from typing import Generator

from src.data.models import Base  # Your SQLAlchemy Base
from main import app as flask_app  # Your Flask app instance
# from main import init_db_main # We won't call this directly, engine is managed by fixtures
from src.config import settings # Direct import if get_settings() is problematic in test setup phase

@pytest.fixture(scope="session")
def db_engine():
    """
    Fixture for a test database engine (in-memory SQLite).
    Creates all tables once per session.
    """
    test_db_url = "sqlite:///:memory:"
    # Forcing a change to the settings object if main.py's engine relies on it at import time
    # This is a bit of a hack; app factories are cleaner for this.
    original_db_url = settings.database_url
    settings.database_url = test_db_url

    engine = create_engine(test_db_url, connect_args={"check_same_thread": False}) # check_same_thread for SQLite
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    settings.database_url = original_db_url # Restore original setting if necessary

@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[SQLAlchemySession, None, None]:
    """
    Fixture for a test database session.
    Rolls back transactions after each test to ensure isolation.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    db = SessionLocal()
    
    yield db
    
    db.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_engine): # Depends on db_engine to ensure tables are created and test URL is set
    """
    Fixture for the Flask test client, configured for testing with the in-memory SQLite DB.
    """
    flask_app.config['TESTING'] = True
    # Override the DATABASE_URL directly in the app's config if it uses it for session creation.
    # The main.py creates its engine based on settings.database_url.
    # The db_engine fixture already updates settings.database_url for its scope.
    
    # Ensure the app's global engine is the test engine.
    # This is crucial if @before_request in main.py uses a global app.engine.
    # Re-assigning flask_app.engine from main.py
    if hasattr(flask_app, 'engine'):
        flask_app.engine.dispose() # Dispose old engine if exists
    flask_app.engine = db_engine # Use the test engine directly

    with flask_app.test_client() as testing_client:
        with flask_app.app_context():
            # The @before_request in main.py should now use the flask_app.engine (test_engine)
            # to create g.db sessions.
            yield testing_client
