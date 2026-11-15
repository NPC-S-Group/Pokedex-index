"""Mejoras tras la revisión del 15 nov: equipos coherentes, nombres limpios y fechas."""

from datetime import UTC, datetime, timedelta

import pytest

POKEDEX = "/api/v1/pokedex"
TEAMS = "/api/v1/teams"


def _equipo(client, headers, ids, name="Equipo Elite"):
    return client.post(TEAMS, json={"name": name, "pokemon_ids": ids}, headers=headers)


# ─────────────── 1. Un equipo nunca se queda vacío ───────────────


def test_no_se_borra_el_unico_pokemon_de_un_equipo(
    client, auth_headers, test_user, add_to_pokedex
):
    (charmander,) = add_to_pokedex(test_user, 4)
    team_id = _equipo(client, auth_headers, [4], name="Solo fuego").json()["id"]
    r = client.delete(f"{POKEDEX}/{charmander.id}", headers=auth_headers)
    assert r.status_code == 409
    assert "Solo fuego" in r.json()["detail"]
    # No ha cambiado nada: sigue en la Pokédex y en el equipo.
    assert client.get(f"{POKEDEX}/{charmander.id}", headers=auth_headers).status_code == 200
    miembros = client.get(f"{TEAMS}/{team_id}", headers=auth_headers).json()["members"]
    assert [m["pokemon_id"] for m in miembros] == [4]


def test_se_puede_borrar_si_el_equipo_tiene_mas(
    client, auth_headers, test_user, add_to_pokedex
):
    pikachu, bulbasaur, charmander = add_to_pokedex(test_user, 25, 1, 4)
    team_id = _equipo(client, auth_headers, [25, 1, 4]).json()["id"]
    assert client.delete(f"{POKEDEX}/{bulbasaur.id}", headers=auth_headers).status_code == 204
    miembros = client.get(f"{TEAMS}/{team_id}", headers=auth_headers).json()["members"]
    # Sale del equipo y las posiciones se renumeran sin huecos.
    assert [(m["position"], m["pokemon_id"]) for m in miembros] == [(1, 25), (2, 4)]


def test_borrar_el_equipo_permite_borrar_el_pokemon(
    client, auth_headers, test_user, add_to_pokedex
):
    (charmander,) = add_to_pokedex(test_user, 4)
    team_id = _equipo(client, auth_headers, [4]).json()["id"]
    assert client.delete(f"{TEAMS}/{team_id}", headers=auth_headers).status_code == 204
    assert client.delete(f"{POKEDEX}/{charmander.id}", headers=auth_headers).status_code == 204


def test_export_de_un_equipo_vacio_antiguo_da_409(
    client, auth_headers, test_user, session
):
    # Equipos vacíos guardados antes del arreglo: el PDF no se genera vacío.
    from app.models import Team

    equipo = Team(trainer_id=test_user.id, name="Vacío")
    session.add(equipo)
    session.commit()
    r = client.get(f"{TEAMS}/{equipo.id}/export", headers=auth_headers)
    assert r.status_code == 409


# ─────────────── 5. Nombres sin espacios vacíos ni tabuladores ───────────────


@pytest.mark.parametrize("nombre", ["", "   ", "\t", "Equipo\tElite", "Linea\nnueva"])
def test_nombre_de_equipo_no_valido(client, auth_headers, test_user, add_to_pokedex, nombre):
    add_to_pokedex(test_user, 25)
    assert _equipo(client, auth_headers, [25], name=nombre).status_code == 422


def test_nombre_de_equipo_se_limpia(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    r = client.post(
        TEAMS,
        json={"name": "  Kanto  ", "description": "   ", "pokemon_ids": [25]},
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["name"] == "Kanto"
    assert r.json()["description"] is None


def test_put_tambien_limpia_el_nombre(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    team_id = _equipo(client, auth_headers, [25]).json()["id"]
    r = client.put(
        f"{TEAMS}/{team_id}", json={"name": "   ", "pokemon_ids": [25]}, headers=auth_headers
    )
    assert r.status_code == 422


def test_mote_se_limpia_y_no_admite_tabuladores(client, auth_headers, test_user, add_to_pokedex):
    (entrada,) = add_to_pokedex(test_user, 25)
    url = f"{POKEDEX}/{entrada.id}"
    r = client.patch(url, json={"nickname": "  Sparky  "}, headers=auth_headers)
    assert r.json()["nickname"] == "Sparky"
    assert client.patch(url, json={"nickname": "a\tb"}, headers=auth_headers).status_code == 422
    # Un mote de solo espacios equivale a no tener mote.
    assert client.patch(url, json={"nickname": "   "}, headers=auth_headers).json()["nickname"] is None


def test_mote_al_anadir(client, auth_headers):
    r = client.post(POKEDEX, json={"pokemon_id": 25, "nickname": " Rayo "}, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["nickname"] == "Rayo"


# ─────────────── 4. Sin fechas de captura en el futuro ───────────────


def test_fecha_de_captura_futura(client, auth_headers, test_user, add_to_pokedex):
    (entrada,) = add_to_pokedex(test_user, 25)
    url = f"{POKEDEX}/{entrada.id}"
    for fecha in ("2030-01-01T00:00:00Z", "2099-12-31"):
        r = client.patch(url, json={"is_captured": True, "capture_date": fecha}, headers=auth_headers)
        assert r.status_code == 422, fecha


def test_fecha_de_captura_pasada_o_actual(client, auth_headers, test_user, add_to_pokedex):
    (entrada,) = add_to_pokedex(test_user, 25)
    url = f"{POKEDEX}/{entrada.id}"
    ayer = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert client.patch(url, json={"capture_date": ayer}, headers=auth_headers).status_code == 200
    # Un reloj del cliente un par de minutos adelantado no es un error.
    casi_ahora = (datetime.now(UTC) + timedelta(minutes=2)).isoformat()
    assert client.patch(url, json={"capture_date": casi_ahora}, headers=auth_headers).status_code == 200


# ─────────────── 3 y 6. Búsqueda: formas especiales y nombres con signos ───────────────

import httpx  # noqa: E402

from app.dependencies import get_pokeapi_service  # noqa: E402
from app.main import app  # noqa: E402
from app.services.pokeapi_service import PokeAPIService, nombre_a_slug  # noqa: E402

BASE = "https://pokeapi.test/api/v2"
LISTADO = {
    25: "pikachu",
    29: "nidoran-f",
    32: "nidoran-m",
    83: "farfetchd",
    122: "mr-mime",
    439: "mime-jr",
    669: "flabebe",
    772: "type-null",
    10080: "pikachu-rock-star",
    10081: "pikachu-belle",
}


def _manejador(peticiones):
    def manejar(request: httpx.Request) -> httpx.Response:
        peticiones.append(request.url.path)
        if request.url.path == "/api/v2/pokemon":
            return httpx.Response(
                200,
                json={
                    "count": len(LISTADO),
                    "results": [
                        {"name": n, "url": f"{BASE}/pokemon/{i}/"} for i, n in LISTADO.items()
                    ],
                },
            )
        return httpx.Response(404, text="Not Found")

    return manejar


@pytest.fixture
def servicio():
    PokeAPIService.limpiar_cache()
    peticiones = []
    poke = PokeAPIService(BASE, transport=httpx.MockTransport(_manejador(peticiones)))
    poke.peticiones = peticiones
    yield poke
    PokeAPIService.limpiar_cache()


@pytest.mark.parametrize(
    ("escrito", "slug"),
    [
        ("Mr. Mime", "mr-mime"),
        ("mr mime", "mr-mime"),
        ("Mime Jr.", "mime-jr"),
        ("Farfetch'd", "farfetchd"),
        ("Farfetch’d", "farfetchd"),
        ("Nidoran♀", "nidoran-f"),
        ("nidoran♂", "nidoran-m"),
        ("Flabébé", "flabebe"),
        ("Type: Null", "type-null"),
        ("  PIKACHU ", "pikachu"),
        (25, "25"),
    ],
)
def test_nombre_a_slug(escrito, slug):
    assert nombre_a_slug(escrito) == slug


@pytest.mark.anyio
async def test_busqueda_sin_formas_especiales_por_defecto(servicio):
    datos = await servicio.buscar(texto="pikachu")
    assert [p["id"] for p in datos["results"]] == [25]
    assert datos["count"] == 1


@pytest.mark.anyio
async def test_busqueda_con_formas_especiales_si_se_piden(servicio):
    datos = await servicio.buscar(texto="pikachu", incluir_formas=True)
    assert [p["id"] for p in datos["results"]] == [25, 10080, 10081]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("escrito", "esperado"),
    [("mr. mime", 122), ("Farfetch'd", 83), ("nidoran♀", 29), ("Flabébé", 669), ("type: null", 772)],
)
async def test_busqueda_con_signos(servicio, escrito, esperado):
    datos = await servicio.buscar(texto=escrito)
    assert [p["id"] for p in datos["results"]] == [esperado]


@pytest.mark.anyio
async def test_detalle_traduce_el_nombre_antes_de_llamar(servicio):
    with pytest.raises(Exception):
        await servicio.get_pokemon("Mr. Mime")  # el simulador responde 404
    assert servicio.peticiones[-1] == "/api/v2/pokemon/mr-mime"


def test_endpoint_acepta_nombres_con_signos(client, auth_headers, servicio):
    app.dependency_overrides[get_pokeapi_service] = lambda: servicio
    for q in ("mr. mime", "farfetch'd", "nidoran♀", "Flabébé", "type: null"):
        r = client.get("/api/v1/pokemon/search", params={"q": q}, headers=auth_headers)
        assert r.status_code == 200, (q, r.text)
        assert r.json()["count"] == 1, q
    r = client.get(
        "/api/v1/pokemon/search",
        params={"q": "pikachu", "include_forms": "true"},
        headers=auth_headers,
    )
    assert r.json()["count"] == 3


@pytest.mark.parametrize("q", ["../ditto", "pika/chu", "<script>", "a;b"])
def test_endpoint_sigue_rechazando_lo_raro(client, auth_headers, q):
    r = client.get("/api/v1/pokemon/search", params={"q": q}, headers=auth_headers)
    assert r.status_code == 422


# ─────────────── Estadísticas más claras ───────────────

from app.services.estadisticas import tipo_mas_comun, tipos_mas_comunes  # noqa: E402


def test_tipos_empatados():
    # charizard (fire/flying), pikachu (electric), pecharunt (poison/ghost)
    tipos = [["fire", "flying"], ["electric"], ["poison", "ghost"]]
    assert tipos_mas_comunes(tipos) == ["electric", "fire", "flying", "ghost", "poison"]
    assert tipo_mas_comun(tipos) == "electric"
    assert tipos_mas_comunes([["fire"], ["fire", "flying"]]) == ["fire"]
    assert tipos_mas_comunes([]) == []


def test_stats_porcentaje_nacional_y_empates(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 4, is_captured=True)  # fire
    add_to_pokedex(test_user, 25, 7)  # electric, water (sin capturar)
    datos = client.get("/api/v1/pokedex/stats", headers=auth_headers).json()
    assert datos["completion_percentage"] == 33.3  # 1 de 3 en TU Pokédex
    assert datos["national_dex_percentage"] == 0.1  # 1 de 1025
    assert datos["most_common_types"] == ["electric", "fire", "water"]
    assert datos["most_common_type"] == "electric"
