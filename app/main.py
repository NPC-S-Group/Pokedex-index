"""Punto de entrada de la API. Base tomada del hito 4 de la práctica guiada."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlmodel import Session

# Importar los modelos registra las tablas antes de create_db_and_tables().
from app import models  # noqa: F401
from app.config import settings
from app.database import create_db_and_tables, engine
from app.limits import limiter
from app.logs import (
    configurar_logging,
    registrar_error_validacion,
    registrar_limite_superado,
    registrar_peticiones,
)
from app.routers import auth, pokedex, pokedex_v2, pokemon, teams
from app.seguridad import cabeceras_seguridad

configurar_logging(settings.log_level, settings.log_file)
logger = logging.getLogger("pokedex_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    logger.info("base de datos lista")
    with Session(engine) as session:
        borrados = auth.borrar_refresh_caducados(session)
    logger.info("refresh tokens caducados borrados: %s", borrados)
    yield
    logger.info("apagando")


app = FastAPI(
    title="Pokédex API",
    version="1.0.4",
    description=(
        "API REST del Pokédex personal · Práctica 1 de Sistemas de Información (UFV).\n\n"
        "Busca Pokémon en la PokeAPI, guarda los tuyos en tu Pokédex y monta equipos "
        "de batalla. **Para probar los endpoints con candado:** regístrate en "
        "`POST /api/v1/auth/register` y pulsa **Authorize** con tu usuario y "
        "contraseña."
    ),
    openapi_tags=[
        {
            "name": "auth",
            "description": "Registro, login con JWT, renovación de la sesión con el "
            "refresh token, logout y tu usuario.",
        },
        {
            "name": "pokemon",
            "description": "Consultas a la PokeAPI: búsqueda por nombre y tipo, "
            "detalle de un Pokémon y su ficha en PDF.",
        },
        {
            "name": "pokedex",
            "description": "Tu Pokédex personal: añadir, ver, editar y borrar "
            "Pokémon, estadísticas y exportación a CSV o PDF. Solo ves lo tuyo.",
        },
        {
            "name": "teams",
            "description": "Equipos de batalla de 1 a 6 Pokémon de tu Pokédex, y "
            "su exportación en PDF con las estadísticas combinadas.",
        },
        {
            "name": "pokedex v2",
            "description": "Ejemplo de versión 2 de la Pokédex: misma información con "
            "otro formato de respuesta. Ver «Versionado» en el README.",
        },
        {"name": "sistema", "description": "Estado de la API."},
    ],
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # PUT hace falta para actualizar equipos desde un navegador.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    # Sin esto, el JavaScript de otra web no puede leer los avisos de deprecación.
    expose_headers=["Deprecation", "Sunset", "Link"],
)

# Límites por endpoint (@limiter.limit) y por defecto (default_limits) en app/limits.py.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, registrar_limite_superado)
app.add_middleware(SlowAPIMiddleware)

# Cabeceras de seguridad (app/seguridad.py) en todas las respuestas.
app.middleware("http")(cabeceras_seguridad)

# Logging (app/logs.py): se añade el último para ser el más externo y ver todas
# las respuestas, también las de CORS y las 429.
app.add_exception_handler(RequestValidationError, registrar_error_validacion)
app.middleware("http")(registrar_peticiones)


for modulo in (auth, pokemon, pokedex, teams):
    app.include_router(modulo.router, prefix="/api/v1")

# API v2 de ejemplo (#14): convive con la v1, que no cambia.
app.include_router(pokedex_v2.router, prefix="/api/v2")


@app.get("/health", summary="Comprobar que la API está viva", tags=["sistema"])
def health():  # sin límite: la usan los monitores
    respuesta = {"status": "ok"}
    # Render pone el commit desplegado en RENDER_GIT_COMMIT. El CI lo usa para saber
    # cuándo ya se sirve la versión nueva y lanzar la prueba de humo (scripts/).
    if commit := os.getenv("RENDER_GIT_COMMIT"):
        respuesta["commit"] = commit
    return respuesta
