"""API v2 de ejemplo de la Pokédex (#14): mismos datos que la v1, otro contrato.

Cambios respecto a /api/v1/pokedex (incompatibles, por eso es otra versión):
- El listado va en un sobre con la paginación: {items, total, limit, offset, has_more}.
- Cada entrada agrupa los datos del Pokémon en «pokemon: {id, name, sprite}».
- is_captured → captured y capture_date → captured_at.

La v1 sigue igual. Los filtros, el orden y la comprobación de propiedad se
reutilizan de la v1: la v2 sólo cambia cómo se presenta la respuesta.
"""

from typing import Literal

from fastapi import APIRouter, Query, Request
from sqlmodel import func, select

from app.dependencies import CurrentUser, SessionDep
from app.limits import LIMITE_AUTENTICADO, limiter
from app.models import PokedexEntryV2, PokedexPageV2
from app.routers.pokedex import _consulta_filtrada, _entrada_propia

router = APIRouter(prefix="/pokedex", tags=["pokedex v2"])


@router.get(
    "",
    summary="Ver mi Pokédex (v2: paginación con total y has_more)",
    response_model=PokedexPageV2,
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
    # El total cuenta todo lo que cumple los filtros; el orden no influye.
    total = session.exec(
        select(func.count()).select_from(consulta.order_by(None).subquery())
    ).one()
    entradas = session.exec(consulta.offset(offset).limit(limit)).all()
    return PokedexPageV2(
        items=[PokedexEntryV2.desde(e) for e in entradas],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(entradas) < total,
    )


@router.get(
    "/{entry_id}",
    summary="Ver una entrada de mi Pokédex (v2)",
    response_model=PokedexEntryV2,
)
@limiter.limit(LIMITE_AUTENTICADO)
def detalle(request: Request, entry_id: int, usuario: CurrentUser, session: SessionDep):
    return PokedexEntryV2.desde(_entrada_propia(session, entry_id, usuario))
