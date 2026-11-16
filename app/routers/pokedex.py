"""CRUD de la Pokédex personal: cada usuario sólo ve y toca lo suyo."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import func, select

from app.dependencies import CurrentUser, ServicioPokeAPI, SessionDep
from app.limits import (
    LIMITE_AUTENTICADO,
    LIMITE_EXPORTAR,
    LIMITE_POKEAPI,
    limiter,
)
from app.models import (
    PokedexEntry,
    PokedexEntryCreate,
    PokedexEntryRead,
    PokedexEntryUpdate,
    TOTAL_POKEMON,
    PokedexStats,
    Team,
    TeamMember,
    ahora,
)
from app.services.estadisticas import racha_de_capturas, tipos_mas_comunes
from app.services.export_service import pokedex_a_csv, pokedex_a_pdf
from app.versionado import obsoleta_en_v1

router = APIRouter(prefix="/pokedex", tags=["pokedex"])

# El texto que llega en ?sort= se traduce a columna aquí. Nunca se pega en el SQL.
ORDENABLE = {
    "pokemon_id": PokedexEntry.pokemon_id,
    "pokemon_name": PokedexEntry.pokemon_name,
    "capture_date": PokedexEntry.capture_date,
}


@router.post(
    "",
    summary="Añadir un Pokémon a mi Pokédex",
    response_model=PokedexEntryRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(LIMITE_POKEAPI)  # consulta la PokeAPI para validar el id
async def anadir(
    request: Request,
    datos: PokedexEntryCreate,
    usuario: CurrentUser,
    session: SessionDep,
    poke: ServicioPokeAPI,
):
    ya_esta = session.exec(
        select(PokedexEntry).where(
            PokedexEntry.owner_id == usuario.id,
            PokedexEntry.pokemon_id == datos.pokemon_id,
        )
    ).first()
    if ya_esta:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya está en tu Pokédex")

    info = await poke.get_pokemon(datos.pokemon_id)
    entrada = PokedexEntry(
        **datos.model_dump(),
        owner_id=usuario.id,
        pokemon_name=info["name"],
        pokemon_sprite=info["sprite"],
        pokemon_types=info.get("types") or [],
        capture_date=ahora() if datos.is_captured else None,
    )
    session.add(entrada)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya está en tu Pokédex")
    session.refresh(entrada)
    return entrada


# Listado y detalle tienen sucesora en /api/v2/pokedex: se marcan obsoletos
# (cabeceras Deprecation, Sunset y Link, y tachados en Swagger). Ver app/versionado.py.
@router.get(
    "",
    summary="Ver mi Pokédex (filtros, orden y paginación)",
    response_model=list[PokedexEntryRead],
    deprecated=True,
    dependencies=[Depends(obsoleta_en_v1)],
)
@limiter.limit(LIMITE_AUTENTICADO)
def listar(
    request: Request,
    usuario: CurrentUser,
    session: SessionDep,
    captured: bool | None = None,
    favorite: bool | None = None,
    sort: Literal["pokemon_id", "pokemon_name", "capture_date"] = "pokemon_id",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    consulta = _consulta_filtrada(usuario, captured, favorite, sort, order)
    return session.exec(consulta.offset(offset).limit(limit)).all()


def _consulta_filtrada(usuario, captured, favorite, sort, order):
    """Las entradas del usuario con los filtros y el orden de ?captured=&favorite=&sort=&order=.

    La comparten el listado y la exportación: lo que se ve es lo que se descarga.
    """
    consulta = select(PokedexEntry).where(PokedexEntry.owner_id == usuario.id)
    if captured is not None:
        consulta = consulta.where(PokedexEntry.is_captured == captured)
    if favorite is not None:
        consulta = consulta.where(PokedexEntry.favorite == favorite)
    columna = ORDENABLE[sort]
    return consulta.order_by(columna.desc() if order == "desc" else columna.asc())


# /export va ANTES que /{entry_id}, por lo mismo que /stats.
@router.get(
    "/export",
    summary="Exportar mi Pokédex en CSV o PDF",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {}, "application/pdf": {}},
            "description": "Fichero con la Pokédex filtrada",
        }
    },
)
@limiter.limit(LIMITE_EXPORTAR)
def exportar(
    request: Request,
    usuario: CurrentUser,
    session: SessionDep,
    format: Literal["csv", "pdf"] = "csv",
    captured: bool | None = None,
    favorite: bool | None = None,
    sort: Literal["pokemon_id", "pokemon_name", "capture_date"] = "pokemon_id",
    order: Literal["asc", "desc"] = "asc",
):
    # Sin paginación: se exporta todo lo que cumpla los filtros.
    entradas = session.exec(
        _consulta_filtrada(usuario, captured, favorite, sort, order)
    ).all()
    descarga = {"Content-Disposition": f'attachment; filename="pokedex.{format}"'}

    if format == "csv":
        return Response(
            pokedex_a_csv(entradas),
            media_type="text/csv; charset=utf-8",
            headers=descarga,
        )

    filtros = {"captured": captured, "favorite": favorite}
    aplicados = {k: str(v).lower() for k, v in filtros.items() if v is not None}
    aplicados["orden"] = f"{sort} {order}"
    return Response(
        pokedex_a_pdf(entradas, usuario.username, aplicados),
        media_type="application/pdf",
        headers=descarga,
    )


def _contar(session, *condiciones) -> int:
    consulta = select(func.count()).select_from(PokedexEntry)
    for condicion in condiciones:
        consulta = consulta.where(condicion)
    return session.exec(consulta).one()


# /stats va ANTES que /{entry_id}: si no, FastAPI intentaría leer "stats" como un id.
@router.get(
    "/stats", summary="Ver las estadísticas de mi Pokédex", response_model=PokedexStats
)
@limiter.limit(LIMITE_AUTENTICADO)
def estadisticas(request: Request, usuario: CurrentUser, session: SessionDep):
    mias = PokedexEntry.owner_id == usuario.id
    total = _contar(session, mias)
    capturados = _contar(session, mias, PokedexEntry.is_captured)
    favoritos = _contar(session, mias, PokedexEntry.favorite)
    porcentaje = round(100 * capturados / total, 1) if total else 0.0

    # Solo las dos columnas que hacen falta, no las entradas enteras.
    tipos = session.exec(select(PokedexEntry.pokemon_types).where(mias)).all()
    fechas = session.exec(
        select(PokedexEntry.capture_date).where(mias, PokedexEntry.is_captured)
    ).all()
    empatados = tipos_mas_comunes(tipos)
    return {
        "total_pokemon": total,
        "captured": capturados,
        "favorites": favoritos,
        "completion_percentage": porcentaje,
        "national_dex_percentage": round(100 * capturados / TOTAL_POKEMON, 1),
        "most_common_type": empatados[0] if empatados else None,
        "most_common_types": empatados,
        "capture_streak_days": racha_de_capturas(fechas, datetime.now(UTC).date()),
    }


def _entrada_propia(session, entry_id: int, usuario) -> PokedexEntry:
    entrada = session.get(PokedexEntry, entry_id)
    # 404 también si es de otro: no confirmamos que exista.
    if entrada is None or entrada.owner_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No está en tu Pokédex")
    return entrada


@router.get(
    "/{entry_id}",
    summary="Ver una entrada de mi Pokédex",
    response_model=PokedexEntryRead,
    deprecated=True,
    dependencies=[Depends(obsoleta_en_v1)],
)
@limiter.limit(LIMITE_AUTENTICADO)
def detalle(request: Request, entry_id: int, usuario: CurrentUser, session: SessionDep):
    return _entrada_propia(session, entry_id, usuario)


@router.patch(
    "/{entry_id}",
    summary="Editar una entrada de mi Pokédex",
    response_model=PokedexEntryRead,
)
@limiter.limit(LIMITE_AUTENTICADO)
def actualizar(
    request: Request,
    entry_id: int,
    datos: PokedexEntryUpdate,
    usuario: CurrentUser,
    session: SessionDep,
):
    entrada = _entrada_propia(session, entry_id, usuario)
    cambios = datos.model_dump(exclude_unset=True)
    # Regla de negocio: capturar pone fecha (si no la mandan); soltar la quita.
    if cambios.get("is_captured") is True and "capture_date" not in cambios:
        if entrada.capture_date is None:
            cambios["capture_date"] = ahora()
    elif cambios.get("is_captured") is False:
        cambios["capture_date"] = None
    entrada.sqlmodel_update(cambios)
    session.add(entrada)
    session.commit()
    session.refresh(entrada)
    return entrada


@router.delete(
    "/{entry_id}",
    summary="Borrar una entrada de mi Pokédex",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit(LIMITE_AUTENTICADO)
def borrar(request: Request, entry_id: int, usuario: CurrentUser, session: SessionDep):
    entrada = _entrada_propia(session, entry_id, usuario)
    miembros = session.exec(
        select(TeamMember).where(TeamMember.pokedex_entry_id == entrada.id)
    ).all()
    # Un equipo siempre tiene de 1 a 6 Pokémon: si este es el único de algún equipo,
    # no se borra (409). Hay que quitarlo antes del equipo o borrar el equipo.
    equipos = [session.get(Team, m.team_id) for m in miembros]
    se_quedarian_vacios = [t.name for t in equipos if len(t.members) == 1]
    if se_quedarian_vacios:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Es el único Pokémon de estos equipos: "
            f"{', '.join(se_quedarian_vacios)}. Cámbialo o borra el equipo antes.",
        )
    # Si estaba en otros equipos, sale de ellos y el resto se renumera (1, 2, 3…).
    for miembro, equipo in zip(miembros, equipos):
        session.delete(miembro)
        restantes = sorted(
            (m for m in equipo.members if m.id != miembro.id), key=lambda m: m.position
        )
        for posicion, m in enumerate(restantes, start=1):
            m.position = posicion
            session.add(m)
    session.delete(entrada)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
