"""Equipos de batalla: hasta 6 Pokémon de la propia Pokédex."""

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlmodel import select

from app.dependencies import CurrentUser, ServicioPokeAPI, SessionDep
from app.limits import LIMITE_AUTENTICADO, LIMITE_POKEAPI, limiter
from app.models import (
    PokedexEntry,
    Team,
    TeamCreate,
    TeamMember,
    TeamMemberRead,
    TeamRead,
)
from app.services.equipo_pdf import generar_pdf_equipo

router = APIRouter(prefix="/teams", tags=["teams"])


def _entradas_de_la_pokedex(session, usuario, pokemon_ids: list[int]) -> list[PokedexEntry]:
    """Devuelve las entradas en el mismo orden que pokemon_ids, o 400 si falta alguna."""
    entradas = session.exec(
        select(PokedexEntry).where(
            PokedexEntry.owner_id == usuario.id,
            PokedexEntry.pokemon_id.in_(pokemon_ids),
        )
    ).all()
    por_pokemon = {e.pokemon_id: e for e in entradas}
    faltan = [pid for pid in pokemon_ids if pid not in por_pokemon]
    if faltan:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Estos Pokémon no están en tu Pokédex: {faltan}",
        )
    return [por_pokemon[pid] for pid in pokemon_ids]


def _poner_miembros(team: Team, entradas: list[PokedexEntry]) -> None:
    # La posición sigue el orden en que llegan los ids (1 a 6).
    team.members = [
        TeamMember(pokedex_entry_id=e.id, position=i)
        for i, e in enumerate(entradas, start=1)
    ]


def _a_respuesta(session, team: Team) -> TeamRead:
    ids = [m.pokedex_entry_id for m in team.members]
    entradas = {
        e.id: e
        for e in session.exec(select(PokedexEntry).where(PokedexEntry.id.in_(ids)))
    }
    miembros = [
        TeamMemberRead(
            position=m.position,
            pokedex_entry_id=m.pokedex_entry_id,
            pokemon_id=entradas[m.pokedex_entry_id].pokemon_id,
            pokemon_name=entradas[m.pokedex_entry_id].pokemon_name,
            nickname=entradas[m.pokedex_entry_id].nickname,
            pokemon_sprite=entradas[m.pokedex_entry_id].pokemon_sprite,
        )
        for m in sorted(team.members, key=lambda m: m.position)
    ]
    return TeamRead(
        id=team.id,
        trainer_id=team.trainer_id,
        name=team.name,
        description=team.description,
        created_at=team.created_at,
        members=miembros,
    )


def _equipo_propio(session, team_id: int, usuario) -> Team:
    team = session.get(Team, team_id)
    # 404 también si es de otro: no confirmamos que exista.
    if team is None or team.trainer_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipo no encontrado")
    return team


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(LIMITE_AUTENTICADO)
def crear(request: Request, datos: TeamCreate, usuario: CurrentUser, session: SessionDep):
    entradas = _entradas_de_la_pokedex(session, usuario, datos.pokemon_ids)
    team = Team(trainer_id=usuario.id, name=datos.name, description=datos.description)
    _poner_miembros(team, entradas)
    session.add(team)
    session.commit()
    session.refresh(team)
    return _a_respuesta(session, team)


@router.get("", response_model=list[TeamRead])
@limiter.limit(LIMITE_AUTENTICADO)
def listar(request: Request, usuario: CurrentUser, session: SessionDep):
    equipos = session.exec(
        select(Team).where(Team.trainer_id == usuario.id).order_by(Team.id)
    ).all()
    return [_a_respuesta(session, t) for t in equipos]


@router.get("/{team_id}", response_model=TeamRead)
@limiter.limit(LIMITE_AUTENTICADO)
def detalle(request: Request, team_id: int, usuario: CurrentUser, session: SessionDep):
    return _a_respuesta(session, _equipo_propio(session, team_id, usuario))


@router.put("/{team_id}", response_model=TeamRead)
@limiter.limit(LIMITE_AUTENTICADO)
def actualizar(request: Request, team_id: int, datos: TeamCreate, usuario: CurrentUser, session: SessionDep):
    # PUT reemplaza el equipo entero: nombre, descripción y miembros.
    team = _equipo_propio(session, team_id, usuario)
    entradas = _entradas_de_la_pokedex(session, usuario, datos.pokemon_ids)
    team.name = datos.name
    team.description = datos.description
    _poner_miembros(team, entradas)
    session.add(team)
    session.commit()
    session.refresh(team)
    return _a_respuesta(session, team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(LIMITE_AUTENTICADO)
def borrar(request: Request, team_id: int, usuario: CurrentUser, session: SessionDep):
    team = _equipo_propio(session, team_id, usuario)
    session.delete(team)  # los miembros se borran en cascada
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{team_id}/export",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Equipo en PDF"}
    },
)
@limiter.limit(LIMITE_POKEAPI)  # consulta la PokeAPI por cada miembro
async def exportar(
    request: Request,
    team_id: int,
    usuario: CurrentUser,
    session: SessionDep,
    poke: ServicioPokeAPI,
):
    """Equipo en PDF: portada con estadísticas combinadas y la ficha de cada Pokémon."""
    equipo = _a_respuesta(session, _equipo_propio(session, team_id, usuario))
    if not equipo.members:
        # Solo puede pasar con equipos guardados antes de exigir siempre 1 a 6.
        raise HTTPException(status.HTTP_409_CONFLICT, "El equipo no tiene Pokémon")
    # Los datos y las imágenes de los (hasta 6) miembros se piden a la vez.
    pokemons = await asyncio.gather(
        *(poke.get_pokemon(m.pokemon_id) for m in equipo.members)
    )
    imagenes = await asyncio.gather(
        *(
            poke.descargar_imagen(
                (p.get("sprites") or {}).get("official_artwork") or p.get("sprite")
            )
            for p in pokemons
        )
    )
    miembros = [
        {"position": m.position, "nickname": m.nickname, "pokemon": p, "imagen": img}
        for m, p, img in zip(equipo.members, pokemons, imagenes)
    ]
    pdf = generar_pdf_equipo(equipo.name, equipo.description, miembros)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="equipo-{team_id}.pdf"'},
    )
