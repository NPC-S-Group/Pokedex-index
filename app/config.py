"""Configuración de la aplicación: un único objeto validado que lee .env."""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Los textos de ejemplo de .env.example: si alguien copia el fichero sin cambiarlos,
# cualquiera que lea el repositorio podría firmar tokens válidos.
_CLAVES_DE_EJEMPLO = {
    "pon-aqui-una-clave-larga-y-aleatoria",
    "cambia-esto-por-una-clave-larga-y-aleatoria",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./pokedex.db"
    # Sin valor por defecto, a propósito: si falta en .env, la aplicación no arranca.
    # Mínimo 32 caracteres (256 bits, lo que pide HS256): una clave corta se puede
    # adivinar por fuerza bruta a partir de un token y con ella falsificar cualquiera.
    # Genera una con: python -c "import secrets; print(secrets.token_urlsafe(32))"
    secret_key: str = Field(min_length=32)
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
    # Cuántos proxies de confianza hay delante de la API (Render pone 1). Con 0 se
    # usa la IP de la conexión; con N, la N-ésima empezando por la derecha de
    # X-Forwarded-For, que es la que añadió nuestro proxy y el cliente no puede falsear.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)

    @field_validator("secret_key")
    @classmethod
    def clave_no_de_ejemplo(cls, valor: str) -> str:
        if valor in _CLAVES_DE_EJEMPLO:
            raise ValueError("SECRET_KEY es la de ejemplo: genera una clave propia")
        return valor


settings = Settings()
