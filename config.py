from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "wattpad_clone"
    
    # JWT
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    
    # Admin
    admin_username: str = "admin"
    admin_password: str = "admin123"
    
    # File Upload
    upload_dir: str = "uploads"
    max_file_size: int = 5242880  # 5MB
    allowed_extensions: str = "jpg,jpeg,png,gif,webp"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings():
    return Settings()
