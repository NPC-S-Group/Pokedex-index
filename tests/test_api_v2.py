"""Tests de la API v2 de ejemplo de la Pokédex (#14)."""

from datetime import UTC, datetime

V1 = "/api/v1/pokedex"
V2 = "/api/v2/pokedex"


def _ids(pagina: dict) -> list[int]:
    return [e["pokemon"]["id"] for e in pagina["items"]]


# ───────────────────────────── Listado ─────────────────────────────


def test_listado_vacio(client, auth_headers):
    r = client.get(V2, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
        "has_more": False,
    }


def test_forma_de_cada_entrada(client, auth_headers, test_user, add_to_pokedex):
    fecha = datetime(2026, 1, 15, 10, 30, tzinfo=UTC)
    (entrada,) = add_to_pokedex(
        test_user,
        25,
        nickname="Pika",
        notes="nota",
        is_captured=True,
        favorite=True,
        capture_date=fecha,
    )
    (item,) = client.get(V2, headers=auth_headers).json()["items"]
    assert set(item) == {
        "id",
        "pokemon",
        "nickname",
        "notes",
        "captured",
        "captured_at",
        "favorite",
        "created_at",
    }
    assert item["id"] == entrada.id
    assert item["pokemon"] == {
        "id": 25,
        "name": "pikachu",
        "sprite": "https://sprites.test/25.png",
    }
    assert item["nickname"] == "Pika"
    assert item["notes"] == "nota"
    assert item["captured"] is True
    assert item["captured_at"].startswith("2026-01-15T10:30:00")
    assert item["favorite"] is True
    # No se filtran campos internos ni los nombres de la v1.
    for campo in ("owner_id", "is_captured", "capture_date", "pokemon_name"):
        assert campo not in item


def test_mismos_datos_que_la_v1(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 1, 4, 7, is_captured=True)
    v1 = client.get(V1, headers=auth_headers).json()
    v2 = client.get(V2, headers=auth_headers).json()["items"]
    assert [(e["id"], e["pokemon_id"], e["is_captured"]) for e in v1] == [
        (e["id"], e["pokemon"]["id"], e["captured"]) for e in v2
    ]


def test_solo_lo_mio(client, auth_headers, test_user, other_user, add_to_pokedex):
    add_to_pokedex(test_user, 1, 4)
    add_to_pokedex(other_user, 7, 25, 133)
    pagina = client.get(V2, headers=auth_headers).json()
    assert _ids(pagina) == [1, 4]
    assert pagina["total"] == 2


def test_paginacion(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 1, 4, 7, 25, 133)

    primera = client.get(V2, params={"limit": 2}, headers=auth_headers).json()
    assert _ids(primera) == [1, 4]
    assert primera["total"] == 5
    assert primera["limit"] == 2
    assert primera["offset"] == 0
    assert primera["has_more"] is True

    ultima = client.get(
        V2, params={"limit": 2, "offset": 4}, headers=auth_headers
    ).json()
    assert _ids(ultima) == [133]
    assert ultima["has_more"] is False


def test_pagina_justo_al_final(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 1, 4)
    pagina = client.get(V2, params={"limit": 2}, headers=auth_headers).json()
    assert pagina["has_more"] is False


def test_offset_mas_alla_del_final(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 1, 4)
    pagina = client.get(V2, params={"offset": 10}, headers=auth_headers).json()
    assert pagina["items"] == []
    assert pagina["total"] == 2
    assert pagina["has_more"] is False


def test_total_cuenta_con_los_filtros(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 1, 4, 7, is_captured=True)
    add_to_pokedex(test_user, 25, 133)
    pagina = client.get(
        V2, params={"captured": True, "limit": 1}, headers=auth_headers
    ).json()
    assert _ids(pagina) == [1]
    assert pagina["total"] == 3
    assert pagina["has_more"] is True


def test_filtro_favoritos(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, favorite=True)
    add_to_pokedex(test_user, 1, 4)
    pagina = client.get(V2, params={"favorite": True}, headers=auth_headers).json()
    assert _ids(pagina) == [25]


def test_orden(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, 1, 7)  # pikachu, bulbasaur, squirtle
    pagina = client.get(
        V2, params={"sort": "pokemon_name", "order": "desc"}, headers=auth_headers
    ).json()
    assert [e["pokemon"]["name"] for e in pagina["items"]] == [
        "squirtle",
        "pikachu",
        "bulbasaur",
    ]


def test_parametros_no_validos(client, auth_headers):
    for params in (
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"sort": "owner_id"},
        {"order": "sideways"},
    ):
        assert client.get(V2, params=params, headers=auth_headers).status_code == 422


# ───────────────────────────── Detalle ─────────────────────────────


def test_detalle(client, auth_headers, test_user, add_to_pokedex):
    (entrada,) = add_to_pokedex(test_user, 133, nickname="Eevee")
    r = client.get(f"{V2}/{entrada.id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["pokemon"]["name"] == "eevee"
    assert r.json()["nickname"] == "Eevee"
    assert r.json()["captured"] is False
    assert r.json()["captured_at"] is None


def test_detalle_de_otro_usuario_da_404(
    client, auth_headers, other_user, add_to_pokedex
):
    (ajena,) = add_to_pokedex(other_user, 150)
    assert client.get(f"{V2}/{ajena.id}", headers=auth_headers).status_code == 404


def test_detalle_inexistente(client, auth_headers):
    assert client.get(f"{V2}/9999", headers=auth_headers).status_code == 404


# ───────────────────────────── Convivencia y seguridad ─────────────────────────────


def test_la_v1_no_cambia(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    r = client.get(V1, headers=auth_headers)
    assert isinstance(r.json(), list)
    assert r.json()[0]["pokemon_name"] == "pikachu"
    assert "is_captured" in r.json()[0]


def test_v2_solo_tiene_lectura(client, auth_headers, test_user, add_to_pokedex):
    # Es una v2 de ejemplo: escribir se sigue haciendo por la v1.
    (entrada,) = add_to_pokedex(test_user, 25)
    assert (
        client.post(V2, json={"pokemon_id": 1}, headers=auth_headers).status_code == 405
    )
    r = client.delete(f"{V2}/{entrada.id}", headers=auth_headers)
    assert r.status_code == 405


def test_sin_token(client):
    assert client.get(V2).status_code == 401
    assert client.get(f"{V2}/1").status_code == 401


def test_aparece_en_openapi(client):
    rutas = client.get("/openapi.json").json()["paths"]
    assert "/api/v2/pokedex" in rutas
    assert "/api/v2/pokedex/{entry_id}" in rutas
    assert "/api/v1/pokedex" in rutas


def test_limite_de_100_por_minuto(client, auth_headers):
    for _ in range(100):
        assert client.get(V2, headers=auth_headers).status_code == 200
    assert client.get(V2, headers=auth_headers).status_code == 429
