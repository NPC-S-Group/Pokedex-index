"""Modelos: Base (campos comunes) → Table (la tabla) → Create / Read / Update (los contratos)."""

from datetime import UTC, datetime

from pydantic import EmailStr, field_validator
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def ahora() -> datetime:
    return datetime.now(UTC)


# ───────────────────────────── Usuarios ─────────────────────────────


class UserBase(SQLModel):
    username: str = Field(min_length=3, max_length=50, unique=True, index=True)
    email: EmailStr = Field(unique=True, index=True)


class User(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=ahora)

    entries: list["PokedexEntry"] = Relationship(back_populates="owner")
    teams: list["Team"] = Relationship(back_populates="trainer")


class UserCreate(UserBase):
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_robusta(cls, valor: str) -> str:
        if not any(c.isupper() for c in valor):
            raise ValueError("la contraseña necesita una mayúscula")
        if not any(c.isdigit() for c in valor):
            raise ValueError("la contraseña necesita un número")
        return valor


class UserRead(UserBase):
    # Lo que sale hacia fuera: nunca hashed_password.
    id: int
    created_at: datetime


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
    pokemon_id: int = Field(ge=1, le=1025)


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
    completion_percentage: float  # % de tu Pokédex que está capturado
    most_common_type: str | None  # None si la Pokédex está vacía
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
            return valor.replace(tzinfo=UTC)
        return valor


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
