from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from .models import SeverityEnum

# --- ExternalService Schemas ---


class ExternalServiceBase(BaseModel):
    service_name: str
    provider: Optional[str] = None
    description: Optional[str] = None


class ExternalServiceCreate(ExternalServiceBase):
    pass


class ExternalServiceUpdate(BaseModel):
    service_name: Optional[str] = None
    provider: Optional[str] = None
    description: Optional[str] = None


class ExternalServiceInDBBase(ExternalServiceBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# Public-facing schema for an ExternalService
class ExternalServiceSchema(ExternalServiceInDBBase):
    pass


# For returning a list of services
class ExternalServiceList(BaseModel):
    services: List[ExternalServiceSchema]
    total_count: int


# --- InternalSystem Schemas ---


class InternalSystemBase(BaseModel):
    system_name: str
    responsible_contact: Optional[str] = None
    description: Optional[str] = None


class InternalSystemCreate(InternalSystemBase):
    pass


class InternalSystemUpdate(BaseModel):
    system_name: Optional[str] = None
    responsible_contact: Optional[str] = None
    description: Optional[str] = None


class InternalSystemInDBBase(InternalSystemBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class InternalSystemSchema(InternalSystemInDBBase):
    pass


class InternalSystemList(BaseModel):
    systems: List[InternalSystemSchema]
    total_count: int


# --- Dependency Schemas ---


class DependencyBase(BaseModel):
    internal_system_id: int
    external_service_id: int
    dependency_description: Optional[str] = None


class DependencyCreate(DependencyBase):
    pass


class DependencyUpdate(BaseModel):
    dependency_description: Optional[str] = (
        None  # Typically, only description is updatable for a dependency
    )
    # Changing internal_system_id or external_service_id
    # would usually mean deleting and creating a new dependency.


class DependencyInDBBase(DependencyBase):
    id: int
    # Eager loaded relationships from the CRUD functions will populate these
    internal_system: Optional[InternalSystemSchema] = None
    external_service: Optional[ExternalServiceSchema] = None
    model_config = ConfigDict(from_attributes=True)


class DependencySchema(DependencyInDBBase):
    pass


class DependencyList(BaseModel):
    dependencies: List[DependencySchema]
    total_count: int


# --- Downtime Event Schemas ---


class DowntimeEventSchema(BaseModel):
    id: int
    service_id: int
    service_name: Optional[str] = None
    start_notification_id: int
    end_notification_id: Optional[int] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    severity: Optional[SeverityEnum] = None
    summary: Optional[str] = None
    duration_minutes: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class DowntimeStatsSchema(BaseModel):
    service_id: int
    service_name: Optional[str] = None
    average_minutes: float
    event_count: int
    ongoing_count: int = 0
    has_ongoing: bool = False
