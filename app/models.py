"""Modelos: Base (campos comunes) → Table (la tabla) → Create / Read / Update (los contratos)."""

import re
from datetime import UTC, datetime, timedelta

from pydantic import EmailStr, field_validator
from sqlalchemy import JSON, Column, Index, UniqueConstraint, func
from sqlmodel import Field, Relationship, SQLModel

from app.contrasenas import BCRYPT_MAX_BYTES, demasiado_larga


def ahora() -> datetime:
    return datetime.now(UTC)


# Pokémon de la Pokédex nacional (sin formas especiales, que tienen ids > 10000).
TOTAL_POKEMON = 1025

# Usuarios: letras, números y _ . - (nada de espacios, tabuladores ni saltos de línea).
_USUARIO_VALIDO = re.compile(r"^[A-Za-z0-9_.-]+$")
# Caracteres de control (tabuladores, saltos de línea, etc.).
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def texto_limpio(valor: str | None, campo: str) -> str | None:
    """Quita los espacios de los extremos y rechaza caracteres de control."""
    if valor is None:
        return None
    valor = valor.strip()
    if _CONTROL.search(valor):
        raise ValueError(f"{campo} no puede tener tabuladores ni saltos de línea")
    return valor


# ───────────────────────────── Usuarios ─────────────────────────────


class UserBase(SQLModel):
    username: str = Field(min_length=3, max_length=50, unique=True, index=True)
    email: EmailStr = Field(unique=True, index=True)


class User(UserBase, table=True):
    # «Ash» y «ash» son el mismo usuario: único sin distinguir mayúsculas. Se guarda
    # tal y como lo escribió (para mostrarlo así), pero se compara en minúsculas.
    __table_args__ = (
        Index("ix_user_username_lower", func.lower(Column("username")), unique=True),
    )

    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=ahora)

    entries: list["PokedexEntry"] = Relationship(back_populates="owner")
    teams: list["Team"] = Relationship(back_populates="trainer")


class UserCreate(UserBase):
    password: str = Field(min_length=8)

    @field_validator("username", mode="before")
    @classmethod
    def usuario_limpio(cls, valor):
        # Antes de validar la longitud: «   ab   » no cuenta como 8 caracteres.
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("username")
    @classmethod
    def usuario_valido(cls, valor: str) -> str:
        if not _USUARIO_VALIDO.fullmatch(valor):
            raise ValueError(
                "el usuario solo puede tener letras, números y los signos _ . -"
            )
        return valor

    @field_validator("email", mode="before")
    @classmethod
    def email_limpio(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("email")
    @classmethod
    def email_en_minusculas(cls, valor: str) -> str:
        # Los correos no distinguen mayúsculas: ASH@x.com y ash@x.com son el mismo.
        return valor.lower()

    @field_validator("password")
    @classmethod
    def password_robusta(cls, valor: str) -> str:
        if not any(c.isupper() for c in valor):
            raise ValueError("la contraseña necesita una mayúscula")
        if not any(c.isdigit() for c in valor):
            raise ValueError("la contraseña necesita un número")
        if demasiado_larga(valor):
            # Límite de bcrypt (ver app/auth.py). Sin esto, el registro daba un 500.
            raise ValueError(
                f"la contraseña no puede pasar de {BCRYPT_MAX_BYTES} bytes "
                "(las letras con tilde o la ñ ocupan 2)"
            )
        return valor


class UserRead(UserBase):
    # Lo que sale hacia fuera: nunca hashed_password.
    id: int
    created_at: datetime


class RefreshToken(SQLModel, table=True):
    """Refresh tokens emitidos. La caducidad la marca el propio JWT (exp); aquí solo
    se guarda si existe y si está anulado (revoked_at), porque un JWT no se puede
    «desfirmar»: para anularlo hace falta guardarlo en algún sitio."""

    jti: str = Field(primary_key=True, max_length=32)
    user_id: int = Field(foreign_key="user.id", index=True)
    expires_at: datetime
    created_at: datetime = Field(default_factory=ahora)
    revoked_at: datetime | None = None


class TokenPair(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(SQLModel):
    refresh_token: str = Field(min_length=1, max_length=2000)


# ───────────────────────────── Pokédex ─────────────────────────────


class PokedexEntryBase(SQLModel):
    nickname: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=500)
    is_captured: bool = False
    favorite: bool = False


class PokedexEntry(PokedexEntryBase, table=True):
    __table_args__ = (
        UniqueConstraint("owner_id", "pokemon_id", name="uq_pokedex_owner_pokemon"),
    )

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    pokemon_id: int = Field(index=True)
    pokemon_name: str
    pokemon_sprite: str | None = None
    # Tipos del Pokémon ("fire", "flying"…), copiados de la PokeAPI al añadirlo:
    # así /stats calcula el tipo más común sin llamar fuera. Lista en JSON.
    pokemon_types: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, default=list)
    )
    capture_date: datetime | None = None
    created_at: datetime = Field(default_factory=ahora)

    owner: User | None = Relationship(back_populates="entries")


class PokedexEntryCreate(PokedexEntryBase):
    pokemon_id: int = Field(ge=1, le=TOTAL_POKEMON)

    @field_validator("nickname")
    @classmethod
    def mote_limpio(cls, valor: str | None) -> str | None:
        return texto_limpio(valor, "el mote") or None


class PokedexEntryRead(PokedexEntryBase):
    id: int
    owner_id: int
    pokemon_id: int
    pokemon_name: str
    pokemon_sprite: str | None
    pokemon_types: list[str] = []
    capture_date: datetime | None
    created_at: datetime


class PokedexStats(SQLModel):
    total_pokemon: int
    captured: int
    favorites: int
    completion_percentage: float  # % de TU Pokédex que está capturado
    # % de los 1025 Pokémon de la Pokédex nacional que has capturado.
    national_dex_percentage: float
    # Si hay empate, el primero en orden alfabético (ver most_common_types).
    most_common_type: str | None  # None si la Pokédex está vacía
    most_common_types: list[str]  # todos los empatados en el primer puesto
    capture_streak_days: int  # días seguidos con alguna captura, hasta hoy o ayer


class PokedexEntryUpdate(SQLModel):
    # Todo opcional: PATCH sólo toca lo que llega.
    nickname: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=500)
    is_captured: bool | None = None
    favorite: bool | None = None
    capture_date: datetime | None = None

    @field_validator("capture_date")
    @classmethod
    def fecha_con_zona(cls, valor: datetime | None) -> datetime | None:
        # Una fecha sin zona horaria («2026-01-15T10:00:00») se toma como UTC.
        # Sin esto la base de datos la rechaza y la API devolvía un 500.
        if valor is not None and valor.tzinfo is None:
            valor = valor.replace(tzinfo=UTC)
        # 5 minutos de margen por si el reloj del cliente va un poco adelantado.
        if valor is not None and valor > ahora() + timedelta(minutes=5):
            raise ValueError("la fecha de captura no puede ser futura")
        return valor

    @field_validator("nickname")
    @classmethod
    def mote_limpio(cls, valor: str | None) -> str | None:
        return texto_limpio(valor, "el mote") or None


# ───────────────────────────── Equipos ─────────────────────────────


class Team(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    trainer_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(max_length=100)
    description: str | None = None
    created_at: datetime = Field(default_factory=ahora)

    trainer: User | None = Relationship(back_populates="teams")
    members: list["TeamMember"] = Relationship(
        back_populates="team", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class TeamMember(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    team_id: int = Field(foreign_key="team.id", index=True)
    pokedex_entry_id: int = Field(foreign_key="pokedexentry.id")
    position: int = Field(ge=1, le=6)

    team: Team | None = Relationship(back_populates="members")


class TeamBase(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class TeamCreate(TeamBase):
    # Ids de Pokémon (los de la PokeAPI) que ya están en la Pokédex del usuario.
    pokemon_ids: list[int] = Field(min_length=1, max_length=6)

    # Solo en lo que entra (TeamCreate), no en TeamRead: un equipo ya guardado con un
    # nombre raro se sigue pudiendo leer.
    @field_validator("name", mode="before")
    @classmethod
    def nombre_limpio(cls, valor):
        # Antes de validar la longitud: «   » se queda en «» y da 422.
        return texto_limpio(valor, "el nombre") if isinstance(valor, str) else valor

    @field_validator("description", mode="before")
    @classmethod
    def descripcion_limpia(cls, valor):
        if isinstance(valor, str):
            return valor.strip() or None
        return valor

    @field_validator("pokemon_ids")
    @classmethod
    def sin_repetidos(cls, valor: list[int]) -> list[int]:
        if len(set(valor)) != len(valor):
            raise ValueError("un Pokémon no puede estar dos veces en el equipo")
        return valor


class TeamMemberRead(SQLModel):
    position: int
    pokedex_entry_id: int
    pokemon_id: int
    pokemon_name: str
    nickname: str | None
    pokemon_sprite: str | None


class TeamRead(TeamBase):
    id: int
    trainer_id: int
    created_at: datetime
    members: list[TeamMemberRead]


# ──────────────────────── PokeAPI (solo respuestas) ────────────────────────
# No son tablas: describen lo que devuelve /pokemon para que salga en /docs.


class PokemonSprites(SQLModel):
    front_default: str | None = None
    back_default: str | None = None
    front_shiny: str | None = None
    official_artwork: str | None = None


class PokemonAbility(SQLModel):
    name: str
    is_hidden: bool = False


class PokemonStats(SQLModel):
    hp: int | None = None
    attack: int | None = None
    defense: int | None = None
    special_attack: int | None = None
    special_defense: int | None = None
    speed: int | None = None


class PokemonDetail(SQLModel):
    id: int
    name: str
    sprite: str | None = None
    sprites: PokemonSprites = PokemonSprites()
    types: list[str] = []
    height_m: float | None = None
    weight_kg: float | None = None
    abilities: list[PokemonAbility] = []
    stats: PokemonStats = PokemonStats()


class PokemonSummary(SQLModel):
    id: int
    name: str
    sprite: str | None = None


class PokemonSearchPage(SQLModel):
    count: int
    limit: int
    offset: int
    results: list[PokemonSummary]


# ──────────────────────── API v2 (solo respuestas) ────────────────────────
# La v2 cambia la forma de la respuesta, no las tablas: mismos datos, otro contrato.


class PokemonResumenV2(SQLModel):
    id: int
    name: str
    sprite: str | None


class PokedexEntryV2(SQLModel):
    id: int
    pokemon: PokemonResumenV2
    nickname: str | None
    notes: str | None
    captured: bool
    captured_at: datetime | None
    favorite: bool
    created_at: datetime

    @classmethod
    def desde(cls, entrada: PokedexEntry) -> "PokedexEntryV2":
        return cls(
            id=entrada.id,
            pokemon=PokemonResumenV2(
                id=entrada.pokemon_id,
                name=entrada.pokemon_name,
                sprite=entrada.pokemon_sprite,
            ),
            nickname=entrada.nickname,
            notes=entrada.notes,
            captured=entrada.is_captured,
            captured_at=entrada.capture_date,
            favorite=entrada.favorite,
            created_at=entrada.created_at,
        )


class PokedexPageV2(SQLModel):
    items: list[PokedexEntryV2]
    total: int  # entradas que cumplen los filtros, no sólo las de esta página
    limit: int
    offset: int
    has_more: bool
