from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "pruebaMovink API"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/movink"
    redis_url: str = "redis://localhost:6379/0"

    cache_ttl_seconds: int = 60
    sse_heartbeat_seconds: int = 15
    outbox_poll_seconds: int = 5
    outbox_stream: str = "dashboard:events"

    # Origenes del frontend autorizados por CORS, separados por coma. En dev el
    # front pasa por el proxy de Vite (mismo origen) y esto no hace falta; se
    # usa cuando el front se sirve desde otro origen (`vite preview`, build
    # estatico, otro host).
    cors_origins: str = "http://localhost:5173,http://localhost:4173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
