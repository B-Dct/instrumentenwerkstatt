"""Zentrale Konfiguration – liest Werte aus der .env-Datei im backend-Ordner."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str


settings = Settings()
