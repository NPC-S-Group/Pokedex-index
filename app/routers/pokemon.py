"""Proxy de consulta a la PokeAPI."""

from fastapi import APIRouter, Request

from app.dependencies import CurrentUser, ServicioPokeAPI
from app.limits import LIMITE_POKEAPI, limiter

router = APIRouter(prefix="/pokemon", tags=["pokemon"])


@router.get("/{id_or_name}")
@limiter.limit(LIMITE_POKEAPI)
async def consultar_pokemon(
    request: Request,
    id_or_name: str, usuario: CurrentUser, poke: ServicioPokeAPI
):
    return await poke.get_pokemon(id_or_name)
