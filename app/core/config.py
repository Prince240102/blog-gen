from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""

    # Search APIs
    brave_api_key: Optional[str] = None
    serper_api_key: Optional[str] = None

    # WordPress
    wordpress_url: Optional[str] = None
    # Public URL used for permalinks/admin links returned to the browser.
    # Example: http://10.0.0.193:18888
    wordpress_public_url: Optional[str] = None
    wordpress_username: Optional[str] = None
    wordpress_app_password: Optional[str] = None

    # Auth
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    model_config = {"env_file": ".env"}


settings = Settings()
