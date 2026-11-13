"""Motor de base de datos y sesión por petición."""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

logger = logging.getLogger("pokedex_api")

# check_same_thread=False: FastAPI atiende cada petición en un hilo distinto
# y SQLite, por defecto, sólo deja usar la conexión al hilo que la abrió.
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})

# Columnas añadidas después de crear la tabla. create_all() crea las tablas que
# faltan, pero no añade columnas a una tabla que ya existe: sin esto, una base de
# datos creada antes daría «no such column» en cuanto se leyera la Pokédex.
COLUMNAS_NUEVAS = {
    ("pokedexentry", "pokemon_types"): "JSON NOT NULL DEFAULT '[]'",  # #12
}


def create_db_and_tables(motor: Engine = engine) -> None:
    SQLModel.metadata.create_all(motor)
    _anadir_columnas_nuevas(motor)


def _anadir_columnas_nuevas(motor: Engine) -> None:
    inspector = inspect(motor)
    with motor.begin() as conexion:
        for (tabla, columna), definicion in COLUMNAS_NUEVAS.items():
            existentes = {c["name"] for c in inspector.get_columns(tabla)}
            if columna not in existentes:
                # Nombres fijos de este diccionario, nunca texto de un usuario.
                conexion.execute(
                    text(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
                )
                logger.info("columna añadida: %s.%s", tabla, columna)


def get_session():
    # Una sesión por petición; el with la cierra pase lo que pase.
    with Session(engine) as session:
        yield session
