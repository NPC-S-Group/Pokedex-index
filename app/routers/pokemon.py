"""Consulta a la PokeAPI: búsqueda, detalle y ficha en PDF."""

import re
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.dependencies import CurrentUser, ServicioPokeAPI
from app.limits import LIMITE_POKEAPI, limiter
from app.models import PokemonDetail, PokemonSearchPage
from app.services.ficha_pdf import generar_ficha

router = APIRouter(prefix="/pokemon", tags=["pokemon"])


# /search va ANTES que /{id_or_name}: si no, FastAPI leería "search" como un nombre.
@router.get("/search", response_model=PokemonSearchPage)
@limiter.limit(LIMITE_POKEAPI)
async def buscar_pokemon(
    request: Request,
    usuario: CurrentUser,
    poke: ServicioPokeAPI,
    q: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=50,
            # Letras (con tilde), números, espacios y los signos de nombres como
            # «Mr. Mime», «Farfetch'd», «Type: Null» o «Nidoran♀».
            pattern=r"^[\w .'’:♀♂-]+$",
            description="Parte del nombre, p. ej. 'chu', 'saur' o 'mr. mime'",
        ),
    ] = None,
    tipo: Annotated[
        str | None,
        Query(
            alias="type",
            max_length=20,
            description="Tipo en inglés, p. ej. 'fire' o 'water'",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_forms: Annotated[
        bool,
        Query(
            description="Incluir formas especiales (ids > 1025, p. ej. "
            "'pikachu-rock-star'). No se pueden añadir a la Pokédex."
        ),
    ] = False,
):
    """Busca Pokémon por parte del nombre y/o por tipo, ordenados por número."""
    return await poke.buscar(
        texto=q, tipo=tipo, limit=limit, offset=offset, incluir_formas=include_forms
    )


@router.get("/{id_or_name}", response_model=PokemonDetail)
@limiter.limit(LIMITE_POKEAPI)
async def consultar_pokemon(
    request: Request, id_or_name: str, usuario: CurrentUser, poke: ServicioPokeAPI
):
    """Detalle: tipos, altura, peso, habilidades, sprites y estadísticas base."""
    return await poke.get_pokemon(id_or_name)


@router.get(
    "/{id_or_name}/card",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Ficha en PDF"}
    },
)
@limiter.limit(LIMITE_POKEAPI)
async def ficha_pokemon(
    request: Request, id_or_name: str, usuario: CurrentUser, poke: ServicioPokeAPI
):
    """Ficha del Pokémon en PDF (A5): imagen, tipos, datos y estadísticas con barras."""
    pokemon = await poke.get_pokemon(id_or_name)
    sprites = pokemon.get("sprites") or {}
    imagen = await poke.descargar_imagen(
        sprites.get("official_artwork") or pokemon.get("sprite")
    )
    pdf = generar_ficha(pokemon, imagen)
    nombre = re.sub(r"[^a-z0-9-]", "", pokemon["name"].lower()) or "pokemon"
    return Response(
        content=pdf,
        media_type="application/pdf",
        # attachment: el navegador (y Swagger, con «Download file») lo descarga como fichero.
        headers={"Content-Disposition": f'attachment; filename="{nombre}.pdf"'},
    )
