"""Configuración de la aplicación: un único objeto validado que lee .env."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./pokedex.db"
    # Sin valor por defecto, a propósito: si falta en .env, la aplicación no arranca.
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    pokeapi_base_url: str = "https://pokeapi.co/api/v2"
    pokeapi_timeout: float = 5.0  # segundos; si se supera, la API responde 504
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
