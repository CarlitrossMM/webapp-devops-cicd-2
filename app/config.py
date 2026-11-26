"""Configuración centralizada mediante variables de entorno."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parámetros de configuración de la aplicación."""

    APP_NAME: str = "Inventario ERP"
    APP_VERSION: str = "1.0.0"

    DATABASE_URL: str = "sqlite:///./inventario.db"

    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production-32chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 120

    OTEL_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "inventario-erp"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:5080/api/default"
    OTEL_EXPORTER_OTLP_HEADERS: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
