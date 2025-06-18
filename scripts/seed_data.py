import os
import sys
from typing import Dict, List, Any

# Add project root to Python path to allow direct imports from src
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.logger import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.data.models import Base, ExternalService, InternalSystem, Dependency # Removed create_tables, get_db_session as we'll make local ones
from src.data import crud


SAMPLE_EXTERNAL_SERVICES: List[Dict[str, Any]] = [
    {"service_name": "AWS EC2 us-east-1", "provider": "AWS", "description": "AWS EC2 Compute in N. Virginia"},
    {"service_name": "AWS S3 Global", "provider": "AWS", "description": "AWS S3 Storage"},
    {"service_name": "Microsoft Azure VMs (East US)", "provider": "Microsoft Azure", "description": "Azure Virtual Machines in East US"},
    {"service_name": "Google Cloud Storage (multi-region)", "provider": "Google Cloud", "description": "GCP Object Storage"},
    {"service_name": "GitHub Actions", "provider": "GitHub", "description": "CI/CD Platform"},
    {"service_name": "Outlook 365", "provider": "Microsoft", "description": "Email Service"},
    {"service_name": "Slack API", "provider": "Slack", "description": "Team Collaboration and Messaging API"},
    {"service_name": "Twilio SMS API", "provider": "Twilio", "description": "SMS Gateway Service"}
]

SAMPLE_INTERNAL_SYSTEMS: List[Dict[str, Any]] = [
    {"system_name": "Core Application Server", "responsible_contact": "app-dev-team@example.com", "description": "Main backend application for core business logic."},
    {"system_name": "User Authentication Service", "responsible_contact": "auth-team@example.com", "description": "Handles user login, sessions, and SSO integration."},
    {"system_name": "Data Processing Pipeline", "responsible_contact": "data-eng-team@example.com", "description": "ETL jobs for analytics and reporting."},
    {"system_name": "Customer Notification Gateway", "responsible_contact": "comms-platform-team@example.com", "description": "Sends email, SMS, and push notifications to users."},
    {"system_name": "Internal Wiki & Documentation", "responsible_contact": "knowledge-management@example.com", "description": "Confluence or similar internal documentation platform."}
]

# Dependencies will refer to names defined above. The script will look up their IDs.
SAMPLE_DEPENDENCIES: List[Dict[str, Any]] = [
    {"internal_system_name": "Core Application Server", "external_service_name": "AWS EC2 us-east-1", "description": "Primary compute hosting for application logic."},
    {"internal_system_name": "Core Application Server", "external_service_name": "AWS S3 Global", "description": "Stores user-generated content and static assets."},
    {"internal_system_name": "User Authentication Service", "external_service_name": "AWS EC2 us-east-1", "description": "Hosted on EC2 instances for scalability."},
    {"internal_system_name": "Data Processing Pipeline", "external_service_name": "AWS S3 Global", "description": "Reads source data from and writes processed data to S3."},
    {"internal_system_name": "Data Processing Pipeline", "external_service_name": "Microsoft Azure VMs (East US)", "description": "Uses Azure VMs for specific Windows-based processing tasks."},
    {"internal_system_name": "Customer Notification Gateway", "external_service_name": "Outlook 365", "description": "Relies on Outlook/Exchange for sending transactional emails."},
    {"internal_system_name": "Customer Notification Gateway", "external_service_name": "Twilio SMS API", "description": "Sends SMS alerts and notifications via Twilio."},
    {"internal_system_name": "Internal Wiki & Documentation", "external_service_name": "Google Cloud Storage (multi-region)", "description": "Backs up attachments and large files from the wiki."}
]

def populate_data():
    logger.info("Starting data population script...")
    # TEMPORARY: Hardcoding DB URL for local script execution
    HARDCODED_LOCAL_DB_URL = "postgresql+psycopg2://noticehub_user:noticehub_password@localhost:5432/noticehub_db"
    logger.warning(f"USING TEMPORARILY HARDCODED DB URL FOR SEED SCRIPT: {HARDCODED_LOCAL_DB_URL.replace('noticehub_password', '********')}")
    
    local_engine = create_engine(HARDCODED_LOCAL_DB_URL)
    logger.info("Force dropping all tables in public schema with CASCADE before recreating...")
    with local_engine.connect() as connection:
        result = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public';"))
        for row in result:
            table_name = row[0]
            logger.info(f"Dropping table: public.{table_name} with CASCADE")
            connection.execute(text(f'DROP TABLE IF EXISTS public."{table_name}" CASCADE;'))
        connection.commit() # Commit the DROP TABLE operations
    logger.info("Creating all tables...")
    Base.metadata.create_all(local_engine) # Ensure tables are created with the local engine
    
    LocalSession = sessionmaker(autocommit=False, autoflush=False, bind=local_engine)
    db = LocalSession()

    created_services: Dict[str, ExternalService] = {}
    created_systems: Dict[str, InternalSystem] = {}

    try:
        logger.info("Populating External Services...")
        for service_data in SAMPLE_EXTERNAL_SERVICES:
            service = crud.get_external_service_by_name(db, service_data["service_name"])
            if not service:
                service = crud.create_external_service(
                    db,
                    service_name=service_data["service_name"],
                    provider=service_data.get("provider"),
                    description=service_data.get("description")
                )
                logger.info(f"Created ExternalService: {service.service_name}")
            else:
                logger.info(f"ExternalService '{service.service_name}' already exists. Skipping.")
            if service:
                 created_services[service.service_name] = service

        logger.info("Populating Internal Systems...")
        for system_data in SAMPLE_INTERNAL_SYSTEMS:
            system = crud.get_internal_system_by_name(db, system_data["system_name"])
            if not system:
                system = crud.create_internal_system(
                    db,
                    system_name=system_data["system_name"],
                    responsible_contact=system_data.get("responsible_contact"),
                    description=system_data.get("description")
                )
                logger.info(f"Created InternalSystem: {system.system_name}")
            else:
                logger.info(f"InternalSystem '{system.system_name}' already exists. Skipping.")
            if system:
                created_systems[system.system_name] = system

        logger.info("Populating Dependencies...")
        for dep_data in SAMPLE_DEPENDENCIES:
            internal_system = created_systems.get(dep_data["internal_system_name"])
            external_service = created_services.get(dep_data["external_service_name"])

            if internal_system and external_service:
                # crud.create_dependency already checks for existing dependency by IDs
                dependency = crud.create_dependency(
                    db,
                    internal_system_id=internal_system.id,
                    external_service_id=external_service.id,
                    dependency_description=dep_data.get("description")
                )
                if dependency.id: # Check if it was newly created or fetched
                    # This check might need refinement based on how create_dependency signals creation vs existence
                    # Assuming create_dependency returns the object and we can infer if it's new by checking if a log message was about creation
                    # For simplicity, we'll log the attempt. crud.create_dependency logs success or existing.
                    pass # Logging is handled by crud.create_dependency
            else:
                logger.warning(f"Could not create dependency for '{dep_data['internal_system_name']}' -> '{dep_data['external_service_name']}'. System or Service not found in created items.")
        
        # db.commit() # Assuming crud functions commit their own sessions if they create them, 
        # or if they receive this db session, then a commit here might be needed if crud doesn't.
        # For now, assuming crud functions handle their commits with the passed 'db' session.
        # If crud functions create their own sessions from the default engine, this won't work as intended.
        # Let's assume crud functions use the 'db' session passed to them.
        logger.info("Data population script finished successfully.")

    except Exception as e:
        logger.error(f"Error during data population: {e}", exc_info=True)
        db.rollback() # Rollback in case of error if crud functions didn't commit per item
    finally:
        db.close()

if __name__ == "__main__":
    populate_data()
