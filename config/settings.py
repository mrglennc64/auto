from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str

    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "heyroya-automation"
    minio_region: str = "us-east-1"
    presigned_url_ttl_seconds: int = 604800

    resend_api_key: str = ""
    resend_from: str = "HeyRoya <noreply@heyroya.se>"
    resend_operator_bcc: str = ""

    api_keys: str = ""

    dashboard_user: str = "admin"
    dashboard_pass: str = "changeme"

    public_base_url: str = "http://localhost:8000"
    environment: str = "local"

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


settings = Settings()
