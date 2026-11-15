"""Tests de búsqueda, detalle y ficha en PDF (#8).

Se usa el PokeAPIService de verdad con una PokeAPI simulada (httpx.MockTransport):
así se prueba todo el camino, del endpoint a la "red", sin salir a internet.
"""

import io

import httpx
import pytest
from PIL import Image

from app.dependencies import get_pokeapi_service
from app.main import app
from app.services.ficha_pdf import generar_ficha
from app.services.pokeapi_service import SPRITE_POR_ID, PokeAPIService

BASE = "https://pokeapi.test/api/v2"
ARTE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{id}.png"

LISTADO = {
    1: "bulbasaur",
    2: "ivysaur",
    3: "venusaur",
    4: "charmander",
    25: "pikachu",
    26: "raichu",
    122: "mr-mime",
    133: "eevee",
    172: "pichu",
}
TIPOS = {"fire": [4], "electric": [25, 26, 172], "grass": [1, 2, 3]}


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (247, 208, 44)).save(buffer, format="PNG")
    return buffer.getvalue()


PNG = _png()


def _detalle(pid: int) -> dict:
    return {
        "id": pid,
        "name": LISTADO[pid],
        "height": 4,
        "weight": 60,
        "sprites": {
            "front_default": SPRITE_POR_ID.format(id=pid),
            "other": {"official-artwork": {"front_default": ARTE.format(id=pid)}},
        },
        "abilities": [
            {"ability": {"name": "static"}, "is_hidden": False},
            {"ability": {"name": "lightning-rod"}, "is_hidden": True},
        ],
        "types": [{"type": {"name": "electric"}}],
        "stats": [
            {"base_stat": v, "stat": {"name": n}}
            for n, v in [
                ("hp", 35),
                ("attack", 55),
                ("defense", 40),
                ("special-attack", 50),
                ("special-defense", 50),
                ("speed", 90),
            ]
        ],
    }


class PokeAPISimulada:
    """Responde como la PokeAPI real a las rutas que usamos y apunta cada petición."""

    def __init__(self):
        self.peticiones: list[httpx.Request] = []
        self.imagen = PNG
        self.imagen_status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.peticiones.append(request)
        url = str(request.url)
        ruta = request.url.path.removeprefix("/api/v2")
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(self.imagen_status, content=self.imagen)
        if ruta == "/pokemon":
            return httpx.Response(
                200,
                json={
                    "count": len(LISTADO),
                    "results": [
                        {"name": n, "url": f"{BASE}/pokemon/{i}/"}
                        for i, n in LISTADO.items()
                    ],
                },
            )
        if ruta.startswith("/type/"):
            tipo = ruta.removeprefix("/type/")
            if tipo not in TIPOS:
                return httpx.Response(404, text="Not Found")
            return httpx.Response(
                200,
                json={
                    "pokemon": [
                        {"pokemon": {"name": LISTADO[i], "url": f"{BASE}/pokemon/{i}/"}}
                        for i in TIPOS[tipo]
                    ]
                },
            )
        if ruta.startswith("/pokemon/"):
            clave = ruta.removeprefix("/pokemon/")
            for pid, nombre in LISTADO.items():
                if clave in (str(pid), nombre):
                    return httpx.Response(200, json=_detalle(pid))
            return httpx.Response(404, text="Not Found")
        raise AssertionError(f"ruta inesperada: {url}")

    def contar(self, trozo: str) -> int:
        return sum(trozo in str(p.url) for p in self.peticiones)


@pytest.fixture(autouse=True)
def cache_limpia():
    PokeAPIService.limpiar_cache()
    yield
    PokeAPIService.limpiar_cache()


@pytest.fixture
def pokeapi(client):
    simulada = PokeAPISimulada()
    servicio = PokeAPIService(BASE, transport=httpx.MockTransport(simulada))
    app.dependency_overrides[get_pokeapi_service] = lambda: servicio
    return simulada


def buscar(client, headers, **params):
    return client.get("/api/v1/pokemon/search", params=params, headers=headers)


# --- Búsqueda ------------------------------------------------------------------


def test_busca_por_parte_del_nombre(client, auth_headers, pokeapi):
    r = buscar(client, auth_headers, q="saur")
    assert r.status_code == 200
    datos = r.json()
    assert datos["count"] == 3
    assert [p["name"] for p in datos["results"]] == ["bulbasaur", "ivysaur", "venusaur"]


def test_la_busqueda_no_distingue_mayusculas_y_admite_espacios(
    client, auth_headers, pokeapi
):
    assert (
        buscar(client, auth_headers, q="PIKA").json()["results"][0]["name"] == "pikachu"
    )
    assert buscar(client, auth_headers, q="Mr Mime").json()["results"][0]["id"] == 122


def test_cada_resultado_trae_id_nombre_y_sprite(client, auth_headers, pokeapi):
    [pikachu] = buscar(client, auth_headers, q="pikachu").json()["results"]
    assert pikachu == {
        "id": 25,
        "name": "pikachu",
        "sprite": SPRITE_POR_ID.format(id=25),
    }


def test_busca_por_tipo(client, auth_headers, pokeapi):
    datos = buscar(client, auth_headers, type="electric").json()
    assert [p["id"] for p in datos["results"]] == [25, 26, 172]


def test_combina_nombre_y_tipo(client, auth_headers, pokeapi):
    datos = buscar(client, auth_headers, q="chu", type="electric").json()
    assert [p["name"] for p in datos["results"]] == ["pikachu", "raichu", "pichu"]
    assert pokeapi.contar("/pokemon?") == 0  # con tipo no hace falta el listado


def test_pagina_los_resultados(client, auth_headers, pokeapi):
    datos = buscar(client, auth_headers, limit=2, offset=2).json()
    assert datos["count"] == len(LISTADO)
    assert (datos["limit"], datos["offset"]) == (2, 2)
    assert [p["id"] for p in datos["results"]] == [3, 4]


def test_sin_resultados_devuelve_lista_vacia(client, auth_headers, pokeapi):
    datos = buscar(client, auth_headers, q="digimon").json()
    assert datos["count"] == 0 and datos["results"] == []


def test_tipo_inexistente_da_404(client, auth_headers, pokeapi):
    r = buscar(client, auth_headers, type="sonido")
    assert r.status_code == 404
    assert r.json()["detail"] == "No existe el tipo sonido"


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"q": ""},
        {"q": "../ditto"},
        {"q": "x" * 51},
        {"type": "fi re"},
    ],
)
def test_parametros_no_validos_dan_422(client, auth_headers, pokeapi, params):
    assert buscar(client, auth_headers, **params).status_code == 422
    assert pokeapi.contar("/pokemon?") == 0


def test_el_listado_se_guarda_en_cache(client, auth_headers, pokeapi):
    buscar(client, auth_headers, q="pika")
    buscar(client, auth_headers, q="saur")
    buscar(client, auth_headers, type="fire")
    buscar(client, auth_headers, type="fire")
    assert pokeapi.contar("/pokemon?limit=") == 1
    assert pokeapi.contar("/type/fire") == 1


def test_la_cache_caduca(client, auth_headers, pokeapi, monkeypatch):
    import app.services.pokeapi_service as modulo

    buscar(client, auth_headers, q="pika")
    monkeypatch.setattr(modulo, "CACHE_SEGUNDOS", 0)
    buscar(client, auth_headers, q="pika")
    assert pokeapi.contar("/pokemon?limit=") == 2


def test_listado_con_formato_raro_da_502(client, auth_headers):
    # A cada resultado le falta la "url" de la que sacamos el id.
    servicio = PokeAPIService(
        BASE,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"results": [{"name": "x"}]})
        ),
    )
    app.dependency_overrides[get_pokeapi_service] = lambda: servicio
    assert buscar(client, auth_headers, q="x").status_code == 502


def test_search_no_se_confunde_con_un_nombre(client, auth_headers, pokeapi):
    buscar(client, auth_headers, q="pika")
    assert pokeapi.contar("/pokemon/search") == 0


def test_buscar_exige_token(client, pokeapi):
    assert client.get("/api/v1/pokemon/search?q=pika").status_code == 401


# --- Detalle ---------------------------------------------------------------------


def test_detalle_completo(client, auth_headers, pokeapi):
    r = client.get("/api/v1/pokemon/pikachu", headers=auth_headers)
    assert r.status_code == 200
    datos = r.json()
    assert datos["height_m"] == 0.4
    assert datos["weight_kg"] == 6.0
    assert datos["abilities"] == [
        {"name": "static", "is_hidden": False},
        {"name": "lightning-rod", "is_hidden": True},
    ]
    assert datos["sprites"]["official_artwork"] == ARTE.format(id=25)
    assert datos["stats"]["special_attack"] == 50
    assert datos["types"] == ["electric"]


def test_detalle_de_pokemon_inexistente_da_404(client, auth_headers, pokeapi):
    r = client.get("/api/v1/pokemon/missingno", headers=auth_headers)
    assert r.status_code == 404


# --- Ficha en PDF -----------------------------------------------------------------


def test_ficha_en_pdf(client, auth_headers, pokeapi):
    r = client.get("/api/v1/pokemon/25/card", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="pikachu.pdf"'
    assert r.content.startswith(b"%PDF-")
    assert r.content.rstrip().endswith(b"%%EOF")
    assert b"Ficha de Pikachu" in r.content  # título del documento
    assert pokeapi.contar("official-artwork/25.png") == 1  # usa la ilustración


def test_la_ficha_incluye_la_imagen(client, auth_headers, pokeapi):
    con_imagen = client.get("/api/v1/pokemon/25/card", headers=auth_headers).content
    pokeapi.imagen_status = 404
    sin_imagen = client.get("/api/v1/pokemon/25/card", headers=auth_headers).content
    assert b"/Subtype /Image" in con_imagen
    assert b"/Subtype /Image" not in sin_imagen


def test_ficha_sin_imagen_si_falla_la_descarga(client, auth_headers, pokeapi):
    pokeapi.imagen_status = 500
    r = client.get("/api/v1/pokemon/pikachu/card", headers=auth_headers)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


def test_ficha_sin_imagen_si_la_imagen_esta_rota(client, auth_headers, pokeapi):
    pokeapi.imagen = b"esto no es un png"
    r = client.get("/api/v1/pokemon/pikachu/card", headers=auth_headers)
    assert r.status_code == 200
    assert b"/Subtype /Image" not in r.content


def test_ficha_de_pokemon_inexistente_da_404(client, auth_headers, pokeapi):
    r = client.get("/api/v1/pokemon/missingno/card", headers=auth_headers)
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/json"


def test_ficha_exige_token(client, pokeapi):
    assert client.get("/api/v1/pokemon/25/card").status_code == 401


# --- Piezas sueltas ------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "http://raw.githubusercontent.com/x.png",  # sin https
        "https://evil.example.com/x.png",  # host no permitido
        "https://raw.githubusercontent.com.evil.com/x.png",
    ],
)
async def test_solo_descarga_imagenes_del_repositorio_oficial(url):
    simulada = PokeAPISimulada()
    servicio = PokeAPIService(BASE, transport=httpx.MockTransport(simulada))
    assert await servicio.descargar_imagen(url) is None
    assert simulada.peticiones == []


@pytest.mark.anyio
async def test_no_descarga_imagenes_gigantes():
    simulada = PokeAPISimulada()
    simulada.imagen = b"x" * (2 * 1024 * 1024 + 1)
    servicio = PokeAPIService(BASE, transport=httpx.MockTransport(simulada))
    assert await servicio.descargar_imagen(SPRITE_POR_ID.format(id=25)) is None


@pytest.mark.anyio
async def test_error_de_red_al_descargar_la_imagen():
    def falla(request):
        raise httpx.ConnectError("sin red", request=request)

    servicio = PokeAPIService(BASE, transport=httpx.MockTransport(falla))
    assert await servicio.descargar_imagen(SPRITE_POR_ID.format(id=25)) is None


def test_ficha_con_datos_minimos():
    pdf = generar_ficha({"id": 10001, "name": "forma-rara"})
    assert pdf.startswith(b"%PDF-")
    assert b"Ficha de Forma Rara" in pdf


def test_ficha_con_tipo_desconocido_y_nombre_no_latino():
    pdf = generar_ficha({"id": 1, "name": "ニャース", "types": ["sonido"]})
    assert pdf.startswith(b"%PDF-")
