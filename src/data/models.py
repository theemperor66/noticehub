from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey,
    Enum as SQLAlchemyEnum,
    Index,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func  # For server_default=func.now()
from datetime import datetime
import enum

from src.config import settings
from src.utils.logger import logger

Base = declarative_base()


# --- Enums --- #
class ProcessingStatusEnum(str, enum.Enum):
    UNPROCESSED = "unprocessed"  # Newly created, not yet picked up by LLM
    PENDING_LLM = "pending_llm"  # Picked up, awaiting LLM processing
    PROCESSING_LLM = "processing_llm"  # Currently being processed by LLM
    COMPLETED = "completed"  # LLM processing finished successfully
    ERROR = "error"  # Error during LLM processing
    PENDING_VALIDATION = (
        "pending_validation"  # LLM completed, needs human/rule validation
    )
    MANUAL_REVIEW = "manual_review"  # Flagged for manual review


class NotificationTypeEnum(str, enum.Enum):
    MAINTENANCE = "maintenance"
    OUTAGE = "outage"
    UPDATE = "update"
    ALERT = "alert"
    INFO = "info"
    SECURITY = "security"
    UNKNOWN = "unknown"


class SeverityEnum(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    INFO = "info"  # For informational notifications
    UNKNOWN = "unknown"


class NotificationStatusEnum(str, enum.Enum):
    NEW = "new"  # Notification created, LLM processing not started/pending
    TRIAGED = "triaged"  # LLM processing complete, basic info extracted
    ACTION_PENDING = (
        "action_pending"  # Triaged, and specific actions identified or required
    )
    IN_PROGRESS = "in_progress"  # Actions are being taken
    RESOLVED = "resolved"  # Issue/event resolved, notification closed
    ARCHIVED = "archived"  # Archived for historical purposes
    ERROR_PROCESSING = (
        "error_processing"  # Error during LLM or subsequent processing steps
    )
    PENDING_MANUAL_REVIEW = "pending_manual_review"  # Requires human intervention
    PENDING_VALIDATION = (
        "pending_validation"  # Awaiting validation of LLM output or other data
    )


# --- Models --- #


class RawEmail(Base):
    __tablename__ = "raw_emails"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    original_email_id_hash = Column(
        String(64), unique=True, index=True, nullable=False
    )  # SHA256 hash
    subject = Column(String(1024), nullable=True)
    sender = Column(String(255), nullable=True)
    received_at = Column(DateTime, nullable=False, index=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    has_html_body = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationship (one-to-one with Notification)
    notification = relationship(
        "Notification", back_populates="raw_email_data", uselist=False
    )

    def __repr__(self):
        return f"<RawEmail(id={self.id}, subject='{self.subject}', original_hash='{self.original_email_id_hash[:10]}...')>"


class LLMData(Base):
    __tablename__ = "llm_data"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # LLM Processing Status & Info
    processing_status = Column(
        SQLAlchemyEnum(ProcessingStatusEnum, name="processing_status_enum"),
        default=ProcessingStatusEnum.UNPROCESSED,
        nullable=False,
        index=True,
    )
    error_message = Column(Text, nullable=True)
    raw_llm_response = Column(
        Text, nullable=True
    )  # Store the full JSON/text response from LLM

    # Extracted Fields
    extracted_service_name = Column(String(255), nullable=True, index=True)
    event_start_time = Column(DateTime, nullable=True)
    event_end_time = Column(DateTime, nullable=True)
    notification_type = Column(
        SQLAlchemyEnum(NotificationTypeEnum, name="notification_type_enum"),
        default=NotificationTypeEnum.UNKNOWN,
        nullable=True,
    )
    severity = Column(
        SQLAlchemyEnum(SeverityEnum, name="severity_enum"),
        default=SeverityEnum.UNKNOWN,
        nullable=True,
    )
    llm_summary = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationship (one-to-one with Notification)
    notification = relationship(
        "Notification", back_populates="llm_data", uselist=False
    )

    def __repr__(self):
        return f"<LLMData(id={self.id}, status='{self.processing_status.value}', service='{self.extracted_service_name}')>"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(
        String(1024), nullable=True
    )  # Can be derived from email subject or set manually
    status = Column(
        SQLAlchemyEnum(NotificationStatusEnum, name="notification_status_enum"),
        default=NotificationStatusEnum.NEW,
        nullable=False,
        index=True,
    )

    # Foreign Keys to link RawEmail and LLMData
    raw_email_id = Column(
        Integer, ForeignKey("raw_emails.id"), unique=True, nullable=False, index=True
    )
    llm_data_id = Column(
        Integer, ForeignKey("llm_data.id"), unique=True, nullable=False, index=True
    )

    last_checked_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )  # When the notification was last reviewed/processed by the system
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships (Notification is the owner of the one-to-one)
    raw_email_data = relationship(
        "RawEmail",
        back_populates="notification",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )
    llm_data = relationship(
        "LLMData",
        back_populates="notification",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )

    def __repr__(self):
        return f"<Notification(id={self.id}, title='{self.title}', status='{self.status.value}')>"


class ExternalService(Base):
    __tablename__ = "external_services"
    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String, unique=True, index=True, nullable=False)
    provider = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    dependencies = relationship("Dependency", back_populates="external_service")

    def __repr__(self):
        return f"<ExternalService(id={self.id}, name='{self.service_name}')>"


class InternalSystem(Base):
    __tablename__ = "internal_systems"
    id = Column(Integer, primary_key=True, index=True)
    system_name = Column(String, unique=True, index=True, nullable=False)
    responsible_contact = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    dependencies = relationship("Dependency", back_populates="internal_system")

    def __repr__(self):
        return f"<InternalSystem(id={self.id}, name='{self.system_name}')>"


class Dependency(Base):
    __tablename__ = "dependencies"
    id = Column(Integer, primary_key=True, index=True)
    internal_system_id = Column(
        Integer, ForeignKey("internal_systems.id"), nullable=False
    )
    external_service_id = Column(
        Integer, ForeignKey("external_services.id"), nullable=False
    )
    dependency_description = Column(Text, nullable=True)
    internal_system = relationship("InternalSystem", back_populates="dependencies")
    external_service = relationship("ExternalService", back_populates="dependencies")
    __table_args__ = (
        UniqueConstraint(
            "internal_system_id", "external_service_id", name="_internal_external_uc"
        ),
    )

    def __repr__(self):
        return f"<Dependency(internal_system_id={self.internal_system_id}, external_service_id={self.external_service_id})>"


class NotificationImpact(Base):
    __tablename__ = "notification_impacts"
    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id"), nullable=False)
    internal_system_id = Column(
        Integer, ForeignKey("internal_systems.id"), nullable=False
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    notification = relationship("Notification")
    internal_system = relationship("InternalSystem")

    __table_args__ = (
        UniqueConstraint(
            "notification_id", "internal_system_id", name="_notification_internal_uc"
        ),
    )

    def __repr__(self):
        return f"<NotificationImpact(notification_id={self.notification_id}, internal_system_id={self.internal_system_id})>"


# --- Database Setup --- #
engine = None
SessionLocal = None


def get_db_engine():
    global engine
    if engine is None:
        db_url = settings.database_url
        logger.info(
            f"Connecting to database: {db_url.split('@')[-1] if '@' in db_url else db_url}"
        )
        connect_args = {}
        if db_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            import os

            db_path = db_url.replace("sqlite:///", "")
            if db_path != ":memory:":
                db_dir = os.path.dirname(db_path)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir, exist_ok=True)
                    logger.info(f"Created directory for SQLite DB: {db_dir}")
        engine = create_engine(
            db_url, connect_args=connect_args, echo=settings.db_echo_log
        )
    return engine


def get_db_session():
    global SessionLocal
    if SessionLocal is None:
        db_engine = get_db_engine()
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    return SessionLocal()


def create_tables():
    db_engine = get_db_engine()
    try:
        logger.info("Creating database tables if they don't exist...")
        # The order matters if you have inter-table dependencies not handled by relationship deferral
        # Base.metadata.create_all(db_engine, tables=[RawEmail.__table__, LLMData.__table__, Notification.__table__, ExternalService.__table__, InternalSystem.__table__, Dependency.__table__])
        Base.metadata.create_all(
            db_engine
        )  # Should handle order correctly for SQLAlchemy
        logger.info("Database tables checked/created successfully.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    logger.info(
        "Initializing database and creating tables (if run directly from models.py)..."
    )
    create_tables()
    logger.info("Database table creation process finished.")

    logger.info("Verifying table creation by inspecting metadata...")
    if engine:
        from sqlalchemy import inspect

        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        logger.info(f"Tables present in the database: {table_names}")
        expected_tables = {
            "raw_emails",
            "llm_data",
            "notifications",
            "external_services",
            "internal_systems",
            "dependencies",
            "notification_impacts",
        }
        if expected_tables.issubset(set(table_names)):
            logger.info("All expected tables seem to be created.")
        else:
            logger.warning(
                f"Missing expected tables. Expected: {expected_tables}, Found: {set(table_names)}"
            )
            for table_name in expected_tables:
                if table_name not in table_names:
                    logger.warning(f"Missing table: {table_name}")
    else:
        logger.error("DB engine not initialized, cannot inspect tables.")
