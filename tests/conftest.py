"""Fixtures comunes para todos los tests.

- Base de datos SQLite en memoria, nueva en cada test.
- PokeAPI falsa: los tests no salen a internet.
- El limitador se reinicia en cada test (si no, el registro da 429 al 6.º usuario).

Uso típico:
    def test_algo(client, auth_headers):
        r = client.get("/api/v1/pokedex", headers=auth_headers)

Para tests asíncronos del servicio de PokeAPI: @pytest.mark.anyio
"""

import os

# Antes de importar la app: config.py exige SECRET_KEY.
os.environ.setdefault("SECRET_KEY", "clave-solo-para-tests-nunca-la-real-0123456789")

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import hash_password
from app.database import get_session
from app.dependencies import get_pokeapi_service
from app.limits import limiter
from app.main import app
from app.models import PokedexEntry, User

PASSWORD = "Secreta123"

# Pokémon que conoce la PokeAPI falsa. Cualquier otro id da 404.
POKEMON_FALSOS = {
    1: ("bulbasaur", ["grass", "poison"]),
    4: ("charmander", ["fire"]),
    7: ("squirtle", ["water"]),
    25: ("pikachu", ["electric"]),
    133: ("eevee", ["normal"]),
    143: ("snorlax", ["normal"]),
    150: ("mewtwo", ["psychic"]),
}


class PokeAPIFalsa:
    """Imita a PokeAPIService con datos fijos."""

    async def get_pokemon(self, identificador: int | str) -> dict:
        clave = str(identificador).lower()
        for pid, (nombre, tipos) in POKEMON_FALSOS.items():
            if clave in (str(pid), nombre):
                return {
                    "id": pid,
                    "name": nombre,
                    "sprite": f"https://sprites.test/{pid}.png",
                    "types": tipos,
                    "stats": {"hp": 50, "attack": 50, "defense": 50, "speed": 50},
                }
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"No existe el Pokémon {identificador}"
        )

    async def descargar_imagen(self, url: str | None) -> bytes | None:
        # Sin red: los PDF salen con el hueco de "Sin imagen".
        return None


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # una sola conexión: la BD en memoria no se pierde
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture(autouse=True)
def limitador_limpio():
    limiter.reset()
    yield


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_pokeapi_service] = PokeAPIFalsa
    # Sin "with": no arranca el lifespan, así no se crea la BD real.
    yield TestClient(app)
    app.dependency_overrides.clear()


def _crear_usuario(session, username: str) -> User:
    usuario = User(
        username=username,
        email=f"{username}@test.com",
        hashed_password=hash_password(PASSWORD),
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    return usuario


def _cabeceras(client, username: str) -> dict:
    r = client.post(
        "/api/v1/auth/login", data={"username": username, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def test_user(session) -> User:
    return _crear_usuario(session, "ash")


@pytest.fixture
def auth_headers(client, test_user) -> dict:
    return _cabeceras(client, test_user.username)


@pytest.fixture
def other_user(session) -> User:
    return _crear_usuario(session, "gary")


@pytest.fixture
def other_headers(client, other_user) -> dict:
    return _cabeceras(client, other_user.username)


@pytest.fixture
def add_to_pokedex(session):
    """Mete Pokémon en la Pokédex de un usuario sin pasar por la API.

    add_to_pokedex(test_user, 1, 4, 7) -> lista de PokedexEntry
    """

    def _anadir(usuario: User, *pokemon_ids: int, **campos) -> list[PokedexEntry]:
        entradas = []
        for pid in pokemon_ids:
            nombre, tipos = POKEMON_FALSOS.get(pid, (f"pokemon-{pid}", []))
            entrada = PokedexEntry(
                owner_id=usuario.id,
                pokemon_id=pid,
                pokemon_name=nombre,
                pokemon_sprite=f"https://sprites.test/{pid}.png",
                **{"pokemon_types": tipos, **campos},
            )
            session.add(entrada)
            entradas.append(entrada)
        session.commit()
        for entrada in entradas:
            session.refresh(entrada)
        return entradas

    return _anadir
