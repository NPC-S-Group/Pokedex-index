"""Tests del cliente de la PokeAPI con httpx.MockTransport: nunca salen a internet."""

import logging

import httpx
import pytest
from fastapi import HTTPException

from app.services.pokeapi_service import PokeAPIService

BASE = "https://pokeapi.test/api/v2"

PIKACHU = {
    "id": 25,
    "name": "pikachu",
    "sprites": {"front_default": "https://sprites.test/25.png"},
    "types": [{"slot": 1, "type": {"name": "electric", "url": "..."}}],
    "stats": [
        {"base_stat": 35, "stat": {"name": "hp"}},
        {"base_stat": 55, "stat": {"name": "attack"}},
        {"base_stat": 40, "stat": {"name": "defense"}},
        {"base_stat": 50, "stat": {"name": "special-attack"}},
        {"base_stat": 90, "stat": {"name": "speed"}},
    ],
}


@pytest.fixture
def anyio_backend():
    # Solo asyncio: trio no está instalado.
    return "asyncio"


def servicio(manejador) -> PokeAPIService:
    return PokeAPIService(BASE, timeout=1.0, transport=httpx.MockTransport(manejador))


def responde(status_code=200, **kwargs):
    peticiones = []

    def manejador(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return httpx.Response(status_code, **kwargs)

    manejador.peticiones = peticiones
    return manejador


def lanza(error_cls):
    def manejador(request: httpx.Request) -> httpx.Response:
        raise error_cls("fallo simulado", request=request)

    return manejador


async def falla_con(manejador, identificador="pikachu") -> HTTPException:
    with pytest.raises(HTTPException) as info:
        await servicio(manejador).get_pokemon(identificador)
    return info.value


# --- Caso feliz -------------------------------------------------------------


@pytest.mark.anyio
async def test_simplifica_la_respuesta():
    datos = await servicio(responde(json=PIKACHU)).get_pokemon("pikachu")
    assert datos == {
        "id": 25,
        "name": "pikachu",
        "sprite": "https://sprites.test/25.png",
        "types": ["electric"],
        "stats": {"hp": 35, "attack": 55, "defense": 40, "speed": 90},
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "entrada, ruta",
    [
        (25, "/api/v2/pokemon/25"),
        ("Pikachu", "/api/v2/pokemon/pikachu"),
        ("  MR-MIME ", "/api/v2/pokemon/mr-mime"),
    ],
)
async def test_normaliza_el_identificador(entrada, ruta):
    manejador = responde(json=PIKACHU)
    await servicio(manejador).get_pokemon(entrada)
    assert manejador.peticiones[0].url.path == ruta


@pytest.mark.anyio
async def test_quita_la_barra_final_de_la_base_url():
    manejador = responde(json=PIKACHU)
    poke = PokeAPIService(BASE + "/", transport=httpx.MockTransport(manejador))
    await poke.get_pokemon(25)
    assert str(manejador.peticiones[0].url) == f"{BASE}/pokemon/25"


@pytest.mark.anyio
async def test_sin_sprite_ni_stats_no_rompe():
    bruto = {"id": 10001, "name": "rara", "sprites": {"front_default": None}}
    datos = await servicio(responde(json=bruto)).get_pokemon(10001)
    assert datos["sprite"] is None
    assert datos["types"] == []
    assert datos["stats"] == {
        "hp": None,
        "attack": None,
        "defense": None,
        "speed": None,
    }


# --- Errores de la PokeAPI ----------------------------------------------------


@pytest.mark.anyio
async def test_404_se_traduce_a_404():
    error = await falla_con(responde(404, text="Not Found"), "missingno")
    assert error.status_code == 404
    assert "missingno" in error.detail


@pytest.mark.anyio
@pytest.mark.parametrize("codigo", [400, 429, 500, 503])
async def test_otros_errores_se_traducen_a_502(codigo):
    error = await falla_con(responde(codigo))
    assert error.status_code == 502


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error_cls", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout]
)
async def test_timeout_se_traduce_a_504(error_cls):
    error = await falla_con(lanza(error_cls))
    assert error.status_code == 504
    assert error.detail == "PokeAPI no responde"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error_cls", [httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError]
)
async def test_error_de_red_se_traduce_a_502(error_cls):
    error = await falla_con(lanza(error_cls))
    assert error.status_code == 502
    assert error.detail == "PokeAPI no disponible"


@pytest.mark.anyio
async def test_respuesta_no_json_da_502():
    error = await falla_con(responde(text="<html>mantenimiento</html>"))
    assert error.status_code == 502
    assert error.detail == "Respuesta no válida de PokeAPI"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "cuerpo",
    [
        [1, 2, 3],  # JSON, pero no un objeto
        {"name": "pikachu"},  # falta id
        {"id": 25, "name": "pikachu", "types": [{"slot": 1}]},  # tipo sin nombre
        {"id": 25, "name": "pikachu", "sprites": "no-es-dict"},
    ],
)
async def test_formato_inesperado_da_502(cuerpo):
    error = await falla_con(responde(json=cuerpo))
    assert error.status_code == 502


@pytest.mark.anyio
@pytest.mark.parametrize(
    "identificador", ["", "   ", "../ditto", "pika chu", "pikachu?x=1"]
)
async def test_identificador_no_valido_no_llama_fuera(identificador):
    manejador = responde(json=PIKACHU)
    error = await falla_con(manejador, identificador)
    assert error.status_code == 422
    assert manejador.peticiones == []


# --- Logging ------------------------------------------------------------------


@pytest.mark.anyio
async def test_registra_las_peticiones_correctas(caplog):
    with caplog.at_level(logging.INFO, logger="pokedex_api.pokeapi"):
        await servicio(responde(json=PIKACHU)).get_pokemon(25)
    assert "GET https://pokeapi.test/api/v2/pokemon/25 → 200" in caplog.text


@pytest.mark.anyio
async def test_registra_el_timeout(caplog):
    with caplog.at_level(logging.INFO, logger="pokedex_api.pokeapi"):
        await falla_con(lanza(httpx.ReadTimeout))
    errores = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errores) == 1
    assert "timeout" in errores[0].getMessage()


@pytest.mark.anyio
async def test_registra_los_errores_5xx(caplog):
    with caplog.at_level(logging.INFO, logger="pokedex_api.pokeapi"):
        await falla_con(responde(503))
    assert any(
        r.levelno == logging.ERROR and "503" in r.getMessage() for r in caplog.records
    )


# --- Integración con la app -----------------------------------------------------


def test_la_dependencia_usa_el_timeout_de_la_configuracion(monkeypatch):
    from app import dependencies

    monkeypatch.setattr(dependencies.settings, "pokeapi_timeout", 2.5)
    assert dependencies.get_pokeapi_service().timeout == 2.5
