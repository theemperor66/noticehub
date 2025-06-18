from pydantic import BaseModel, Field, EmailStr, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
import os

# Determine the project root directory. Assumes config.py is in a 'src' subdirectory.
# So, the parent of the parent of this file's directory is the project root.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOTENV_PATH = os.path.join(PROJECT_ROOT, '.env')

class Settings(BaseSettings):
    # Email settings
    email_server: str
    email_port: int
    email_username: str
    email_password: str
    email_folder: str = "INBOX" # Default value example

    # LLM settings
    llm_provider: str = "openai"
    openai_api_key: str
    google_api_key: str | None = None # Optional, can be None if not set
    llm_model: str = "gpt-3.5-turbo"

    # Database settings
    database_url: str # This must be provided in .env
    db_echo_log: bool = Field(False, validation_alias="DB_ECHO_LOG")
    api_port: int = Field(5000, validation_alias="API_PORT")
    debug_mode: bool = Field(False, validation_alias="DEBUG_MODE")
    email_check_interval_seconds: int = Field(60, validation_alias="EMAIL_CHECK_INTERVAL_SECONDS")

    # Email Filtering Configuration
    email_sender_domain_whitelist: Optional[List[str]] = Field(default_factory=list, validation_alias="EMAIL_SENDER_DOMAIN_WHITELIST")
    email_sender_domain_blacklist: Optional[List[str]] = Field(default_factory=list, validation_alias="EMAIL_SENDER_DOMAIN_BLACKLIST")
    email_subject_keywords_whitelist: Optional[List[str]] = Field(default_factory=list, validation_alias="EMAIL_SUBJECT_KEYWORDS_WHITELIST")
    email_subject_keywords_blacklist: Optional[List[str]] = Field(default_factory=list, validation_alias="EMAIL_SUBJECT_KEYWORDS_BLACKLIST")

    @field_validator("email_sender_domain_whitelist", "email_sender_domain_blacklist", 
                     "email_subject_keywords_whitelist", "email_subject_keywords_blacklist", mode='before')
    def _split_str(cls, v):
        if isinstance(v, str):
            return [item.strip().lower() for item in v.split(',') if item.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=DOTENV_PATH,
        env_file_encoding='utf-8',
        extra='ignore'
    )

settings = Settings()
