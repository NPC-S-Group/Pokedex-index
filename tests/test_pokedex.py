"""Tests del CRUD de la Pokédex personal (#7)."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

URL = "/api/v1/pokedex"


def _anadir(client, headers, pokemon_id, **campos):
    return client.post(URL, json={"pokemon_id": pokemon_id, **campos}, headers=headers)


def _ids(respuesta) -> list[int]:
    return [e["pokemon_id"] for e in respuesta.json()]


# ───────────────────────────── POST ─────────────────────────────


def test_anadir_pokemon(client, auth_headers, test_user):
    r = _anadir(client, auth_headers, 25, nickname="Pika", notes="El primero")
    assert r.status_code == 201, r.text
    datos = r.json()
    assert datos["pokemon_id"] == 25
    # Nombre y sprite vienen de la PokeAPI, no del cliente.
    assert datos["pokemon_name"] == "pikachu"
    assert datos["pokemon_sprite"] == "https://sprites.test/25.png"
    assert datos["owner_id"] == test_user.id
    assert datos["nickname"] == "Pika"
    assert datos["notes"] == "El primero"
    assert datos["is_captured"] is False
    assert datos["favorite"] is False
    assert datos["capture_date"] is None


def test_anadir_capturado_pone_fecha(client, auth_headers):
    r = _anadir(client, auth_headers, 4, is_captured=True)
    assert r.status_code == 201
    assert r.json()["capture_date"] is not None


def test_no_se_puede_anadir_dos_veces(client, auth_headers):
    assert _anadir(client, auth_headers, 1).status_code == 201
    r = _anadir(client, auth_headers, 1)
    assert r.status_code == 409


def test_el_mismo_pokemon_en_pokedex_de_dos_usuarios(
    client, auth_headers, other_headers
):
    assert _anadir(client, auth_headers, 7).status_code == 201
    assert _anadir(client, other_headers, 7).status_code == 201


def test_anadir_pokemon_que_no_existe_en_pokeapi(client, auth_headers):
    assert _anadir(client, auth_headers, 999).status_code == 404


def test_anadir_id_fuera_de_rango(client, auth_headers):
    assert _anadir(client, auth_headers, 0).status_code == 422
    assert _anadir(client, auth_headers, 1026).status_code == 422


def test_anadir_nickname_demasiado_largo(client, auth_headers):
    assert _anadir(client, auth_headers, 1, nickname="x" * 51).status_code == 422


def test_anadir_sin_token(client):
    assert client.post(URL, json={"pokemon_id": 1}).status_code == 401


def test_anadir_simultaneo_lo_resuelve_la_bd(
    client, auth_headers, session, monkeypatch
):
    # Otra petición igual se cuela entre la comprobación y el commit: 409, no 500.
    def commit_que_falla():
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(session, "commit", commit_que_falla)
    assert _anadir(client, auth_headers, 1).status_code == 409


# ───────────────────────────── GET lista ─────────────────────────────


def test_listar_vacia(client, auth_headers):
    r = client.get(URL, headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_listar_solo_lo_mio(
    client, auth_headers, test_user, other_user, add_to_pokedex
):
    add_to_pokedex(test_user, 1, 4)
    add_to_pokedex(other_user, 7, 25)
    assert _ids(client.get(URL, headers=auth_headers)) == [1, 4]


def test_filtrar_capturados(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 1, 4, is_captured=True)
    add_to_pokedex(test_user, 7)
    assert _ids(client.get(URL, params={"captured": True}, headers=auth_headers)) == [
        1,
        4,
    ]
    assert _ids(client.get(URL, params={"captured": False}, headers=auth_headers)) == [
        7
    ]


def test_filtrar_favoritos(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, favorite=True)
    add_to_pokedex(test_user, 1, 4)
    r = client.get(URL, params={"favorite": True}, headers=auth_headers)
    assert _ids(r) == [25]


def test_filtros_combinados(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 1, is_captured=True, favorite=True)
    add_to_pokedex(test_user, 4, is_captured=True)
    add_to_pokedex(test_user, 7, favorite=True)
    r = client.get(
        URL, params={"captured": True, "favorite": True}, headers=auth_headers
    )
    assert _ids(r) == [1]


def test_orden_por_defecto_es_pokemon_id(
    client, auth_headers, test_user, add_to_pokedex
):
    add_to_pokedex(test_user, 25, 1, 7)
    assert _ids(client.get(URL, headers=auth_headers)) == [1, 7, 25]


def test_orden_por_nombre(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, 1, 7)  # pikachu, bulbasaur, squirtle
    r = client.get(URL, params={"sort": "pokemon_name"}, headers=auth_headers)
    assert [e["pokemon_name"] for e in r.json()] == ["bulbasaur", "pikachu", "squirtle"]


def test_orden_descendente(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, 1, 7)
    r = client.get(URL, params={"order": "desc"}, headers=auth_headers)
    assert _ids(r) == [25, 7, 1]


def test_orden_por_fecha_de_captura(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(
        test_user, 1, is_captured=True, capture_date=datetime(2026, 3, 1, tzinfo=UTC)
    )
    add_to_pokedex(
        test_user, 4, is_captured=True, capture_date=datetime(2026, 1, 1, tzinfo=UTC)
    )
    add_to_pokedex(
        test_user, 7, is_captured=True, capture_date=datetime(2026, 2, 1, tzinfo=UTC)
    )
    r = client.get(
        URL, params={"sort": "capture_date", "order": "desc"}, headers=auth_headers
    )
    assert _ids(r) == [1, 7, 4]


def test_orden_no_permitido(client, auth_headers):
    # Sólo se aceptan columnas de la lista blanca: nada de SQL desde la URL.
    r = client.get(
        URL, params={"sort": "owner_id; DROP TABLE user"}, headers=auth_headers
    )
    assert r.status_code == 422
    r = client.get(URL, params={"order": "sideways"}, headers=auth_headers)
    assert r.status_code == 422


def test_paginacion(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 1, 4, 7, 25, 133)
    r = client.get(URL, params={"limit": 2, "offset": 1}, headers=auth_headers)
    assert _ids(r) == [4, 7]
    r = client.get(URL, params={"limit": 2, "offset": 4}, headers=auth_headers)
    assert _ids(r) == [133]


def test_paginacion_fuera_de_limites(client, auth_headers):
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert client.get(URL, params=params, headers=auth_headers).status_code == 422


def test_listar_sin_token(client):
    assert client.get(URL).status_code == 401


# ───────────────────────────── GET detalle ─────────────────────────────


def test_detalle(client, auth_headers, test_user, add_to_pokedex):
    (entrada,) = add_to_pokedex(test_user, 133, nickname="Eevee")
    r = client.get(f"{URL}/{entrada.id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["nickname"] == "Eevee"
    assert r.json()["pokemon_name"] == "eevee"


def test_detalle_inexistente(client, auth_headers):
    assert client.get(f"{URL}/9999", headers=auth_headers).status_code == 404


def test_detalle_de_otro_usuario_da_404(
    client, auth_headers, other_user, add_to_pokedex
):
    # 404 y no 403: no confirmamos que la entrada exista.
    (ajena,) = add_to_pokedex(other_user, 150)
    assert client.get(f"{URL}/{ajena.id}", headers=auth_headers).status_code == 404


# ───────────────────────────── PATCH ─────────────────────────────


def test_patch_solo_cambia_lo_enviado(client, auth_headers, test_user, add_to_pokedex):
    (entrada,) = add_to_pokedex(test_user, 25, nickname="Pika", notes="nota")
    r = client.patch(
        f"{URL}/{entrada.id}", json={"favorite": True}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["favorite"] is True
    assert datos["nickname"] == "Pika"
    assert datos["notes"] == "nota"


def test_patch_capturar_pone_fecha(client, auth_headers, test_user, add_to_pokedex):
    (entrada,) = add_to_pokedex(test_user, 25)
    r = client.patch(
        f"{URL}/{entrada.id}", json={"is_captured": True}, headers=auth_headers
    )
    assert r.json()["is_captured"] is True
    assert r.json()["capture_date"] is not None


def test_patch_capturar_respeta_fecha_enviada(
    client, auth_headers, test_user, add_to_pokedex
):
    (entrada,) = add_to_pokedex(test_user, 25)
    r = client.patch(
        f"{URL}/{entrada.id}",
        json={"is_captured": True, "capture_date": "2026-01-15T10:00:00"},
        headers=auth_headers,
    )
    assert r.json()["capture_date"].startswith("2026-01-15T10:00:00")


def test_patch_recapturar_no_cambia_la_fecha(
    client, auth_headers, test_user, add_to_pokedex
):
    fecha = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    (entrada,) = add_to_pokedex(test_user, 25, is_captured=True, capture_date=fecha)
    r = client.patch(
        f"{URL}/{entrada.id}", json={"is_captured": True}, headers=auth_headers
    )
    assert r.json()["capture_date"].startswith("2026-01-01T12:00:00")


def test_patch_soltar_quita_la_fecha(client, auth_headers, test_user, add_to_pokedex):
    (entrada,) = add_to_pokedex(
        test_user, 25, is_captured=True, capture_date=datetime(2026, 1, 1, tzinfo=UTC)
    )
    r = client.patch(
        f"{URL}/{entrada.id}", json={"is_captured": False}, headers=auth_headers
    )
    assert r.json()["is_captured"] is False
    assert r.json()["capture_date"] is None


def test_patch_no_cambia_el_pokemon_ni_el_dueno(
    client, auth_headers, test_user, other_user, add_to_pokedex
):
    # Campos fuera de PokedexEntryUpdate se ignoran.
    (entrada,) = add_to_pokedex(test_user, 25)
    r = client.patch(
        f"{URL}/{entrada.id}",
        json={"pokemon_id": 150, "owner_id": other_user.id},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["pokemon_id"] == 25
    assert r.json()["owner_id"] == test_user.id


def test_patch_fecha_con_zona_horaria(client, auth_headers, test_user, add_to_pokedex):
    (entrada,) = add_to_pokedex(test_user, 25)
    r = client.patch(
        f"{URL}/{entrada.id}",
        json={"is_captured": True, "capture_date": "2026-01-15T10:00:00+00:00"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["capture_date"].startswith("2026-01-15T10:00:00")


def test_patch_nickname_demasiado_largo(
    client, auth_headers, test_user, add_to_pokedex
):
    (entrada,) = add_to_pokedex(test_user, 25)
    r = client.patch(
        f"{URL}/{entrada.id}", json={"nickname": "x" * 51}, headers=auth_headers
    )
    assert r.status_code == 422


def test_patch_de_otro_usuario_da_404(client, auth_headers, other_user, add_to_pokedex):
    (ajena,) = add_to_pokedex(other_user, 150)
    r = client.patch(
        f"{URL}/{ajena.id}", json={"nickname": "Mío"}, headers=auth_headers
    )
    assert r.status_code == 404


# ───────────────────────────── DELETE ─────────────────────────────


def test_borrar(client, auth_headers, test_user, add_to_pokedex):
    (entrada,) = add_to_pokedex(test_user, 25)
    r = client.delete(f"{URL}/{entrada.id}", headers=auth_headers)
    assert r.status_code == 204
    assert r.content == b""
    assert client.get(f"{URL}/{entrada.id}", headers=auth_headers).status_code == 404


def test_borrar_y_volver_a_anadir(client, auth_headers):
    entrada = _anadir(client, auth_headers, 25).json()
    client.delete(f"{URL}/{entrada['id']}", headers=auth_headers)
    assert _anadir(client, auth_headers, 25).status_code == 201


def test_borrar_lo_saca_de_los_equipos(client, auth_headers, test_user, add_to_pokedex):
    pikachu, _ = add_to_pokedex(test_user, 25, 1)
    equipo = client.post(
        "/api/v1/teams",
        json={"name": "Equipo", "pokemon_ids": [25, 1]},
        headers=auth_headers,
    ).json()

    client.delete(f"{URL}/{pikachu.id}", headers=auth_headers)

    r = client.get(f"/api/v1/teams/{equipo['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert [m["pokemon_id"] for m in r.json()["members"]] == [1]


def test_borrar_de_otro_usuario_da_404(
    client, auth_headers, other_headers, other_user, add_to_pokedex
):
    (ajena,) = add_to_pokedex(other_user, 150)
    assert client.delete(f"{URL}/{ajena.id}", headers=auth_headers).status_code == 404
    # Y sigue ahí para su dueño.
    assert client.get(f"{URL}/{ajena.id}", headers=other_headers).status_code == 200


def test_borrar_inexistente(client, auth_headers):
    assert client.delete(f"{URL}/9999", headers=auth_headers).status_code == 404


# ───────────────────────────── /stats básico ─────────────────────────────
# Las estadísticas ampliadas (tipo más común, racha) son de la #12.


def test_stats_vacia(client, auth_headers):
    r = client.get(f"{URL}/stats", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {
        "total_pokemon": 0,
        "captured": 0,
        "favorites": 0,
        "completion_percentage": 0.0,
    }


def test_stats_cuenta_solo_lo_mio(
    client, auth_headers, test_user, other_user, add_to_pokedex
):
    add_to_pokedex(test_user, 1, 4, is_captured=True)
    add_to_pokedex(test_user, 7, favorite=True)
    add_to_pokedex(other_user, 25, 133, is_captured=True)
    r = client.get(f"{URL}/stats", headers=auth_headers)
    assert r.json() == {
        "total_pokemon": 3,
        "captured": 2,
        "favorites": 1,
        "completion_percentage": 66.7,
    }
