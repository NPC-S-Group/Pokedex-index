"""Configuración de la aplicación: un único objeto validado que lee .env."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./pokedex.db"
    # Sin valor por defecto, a propósito: si falta en .env, la aplicación no arranca.
    secret_key: str
    algorithm: str = "HS256"
    # Corto a propósito: tras el logout el access token deja de valer en 30 min como
    # mucho. Para seguir conectado está el refresh token (7 días).
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7  # bonus del enunciado (2.2)
    pokeapi_base_url: str = "https://pokeapi.co/api/v2"
    pokeapi_timeout: float = 5.0  # segundos; si se supera, la API responde 504
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Archivo de log además de la consola. Vacío ("") = solo consola.
    log_file: str | None = "pokedex_api.log"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
