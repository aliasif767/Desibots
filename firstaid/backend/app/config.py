from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "firstaid_db"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama3-70b-8192"
    SCHEDULING_API_URL: str = "http://localhost:8001"
    SECRET_KEY: str = "your-secret-key-change-in-production"

    # Email SMTP Settings
    EMAIL_USER: str = ""
    EMAIL_PASS: str = ""
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SAVE_FOLDER: Optional[str] = None
    IMAP_SERVER: Optional[str] = None
    HOSPITAL_EMAIL: str = "asifali151519@gmail.com"

    class Config:
        env_file = ".env"
        extra = "ignore"  # Allow extra fields in .env without crashing

settings = Settings()
