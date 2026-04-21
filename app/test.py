from app.config import get_settings
s = get_settings()
print(repr(s.snowflake_user))   # Should not be ''
print(repr(s.snowflake_account))

import os
print(os.getcwd())          # Where Python is running from
print(os.path.exists(".env"))  # Is .env found from there?

# config.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # app/ -> agentic-garden/

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
print(BASE_DIR / ".env")  # Should print /path/to/agentic-garden/.env