"""Tests de equipos de batalla (#6)."""

URL = "/api/v1/teams"


def _equipo(client, headers, ids, name="Equipo Elite", description="Mi equipo"):
    return client.post(
        URL,
        json={"name": name, "description": description, "pokemon_ids": ids},
        headers=headers,
    )


def test_crear_equipo(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, 1, 4)
    r = _equipo(client, auth_headers, [25, 1, 4])
    assert r.status_code == 201, r.text
    datos = r.json()
    assert datos["name"] == "Equipo Elite"
    assert datos["trainer_id"] == test_user.id
    # La posición respeta el orden en que se envían los ids.
    assert [(m["position"], m["pokemon_name"]) for m in datos["members"]] == [
        (1, "pikachu"),
        (2, "bulbasaur"),
        (3, "charmander"),
    ]


def test_crear_equipo_de_seis(client, auth_headers, test_user, add_to_pokedex):
    ids = [1, 4, 7, 25, 133, 143]
    add_to_pokedex(test_user, *ids)
    r = _equipo(client, auth_headers, ids)
    assert r.status_code == 201
    assert len(r.json()["members"]) == 6


def test_no_mas_de_seis(client, auth_headers, test_user, add_to_pokedex):
    ids = [1, 4, 7, 25, 133, 143, 150]
    add_to_pokedex(test_user, *ids)
    assert _equipo(client, auth_headers, ids).status_code == 422


def test_equipo_vacio(client, auth_headers):
    assert _equipo(client, auth_headers, []).status_code == 422


def test_sin_repetidos(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    assert _equipo(client, auth_headers, [25, 25]).status_code == 422


def test_pokemon_fuera_de_la_pokedex(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    r = _equipo(client, auth_headers, [25, 150])
    assert r.status_code == 400
    assert "150" in r.json()["detail"]


def test_no_vale_la_pokedex_de_otro(
    client, auth_headers, other_user, add_to_pokedex
):
    add_to_pokedex(other_user, 25)
    assert _equipo(client, auth_headers, [25]).status_code == 400


def test_sin_token(client):
    assert client.get(URL).status_code == 401
    assert _equipo(client, {}, [25]).status_code == 401


def test_listar_solo_los_mios(
    client, auth_headers, other_headers, test_user, other_user, add_to_pokedex
):
    add_to_pokedex(test_user, 25, 1)
    add_to_pokedex(other_user, 4)
    _equipo(client, auth_headers, [25], name="A")
    _equipo(client, auth_headers, [1], name="B")
    _equipo(client, other_headers, [4], name="De Gary")
    r = client.get(URL, headers=auth_headers)
    assert r.status_code == 200
    assert [t["name"] for t in r.json()] == ["A", "B"]


def test_detalle(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    team_id = _equipo(client, auth_headers, [25]).json()["id"]
    r = client.get(f"{URL}/{team_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["members"][0]["pokemon_id"] == 25


def test_actualizar_equipo(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, 1, 4, 7)
    team_id = _equipo(client, auth_headers, [25, 1]).json()["id"]
    r = client.put(
        f"{URL}/{team_id}",
        json={"name": "Nuevo", "description": None, "pokemon_ids": [7, 4, 25]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["name"] == "Nuevo"
    assert datos["description"] is None
    assert [m["pokemon_id"] for m in datos["members"]] == [7, 4, 25]


def test_actualizar_con_pokemon_ajeno(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    team_id = _equipo(client, auth_headers, [25]).json()["id"]
    r = client.put(
        f"{URL}/{team_id}",
        json={"name": "X", "pokemon_ids": [150]},
        headers=auth_headers,
    )
    assert r.status_code == 400
    # El equipo no ha cambiado.
    assert client.get(f"{URL}/{team_id}", headers=auth_headers).json()["name"] == "Equipo Elite"


def test_no_puedo_tocar_equipo_de_otro(
    client, auth_headers, other_headers, other_user, add_to_pokedex
):
    add_to_pokedex(other_user, 25)
    team_id = _equipo(client, other_headers, [25]).json()["id"]
    cuerpo = {"name": "Robado", "pokemon_ids": [25]}
    assert client.get(f"{URL}/{team_id}", headers=auth_headers).status_code == 404
    assert client.put(f"{URL}/{team_id}", json=cuerpo, headers=auth_headers).status_code == 404
    assert client.delete(f"{URL}/{team_id}", headers=auth_headers).status_code == 404


def test_borrar_equipo(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    team_id = _equipo(client, auth_headers, [25]).json()["id"]
    assert client.delete(f"{URL}/{team_id}", headers=auth_headers).status_code == 204
    assert client.get(f"{URL}/{team_id}", headers=auth_headers).status_code == 404


def test_borrar_de_la_pokedex_lo_saca_del_equipo(
    client, auth_headers, test_user, add_to_pokedex
):
    entrada, _ = add_to_pokedex(test_user, 25, 1)
    team_id = _equipo(client, auth_headers, [25, 1]).json()["id"]
    client.delete(f"/api/v1/pokedex/{entrada.id}", headers=auth_headers)
    miembros = client.get(f"{URL}/{team_id}", headers=auth_headers).json()["members"]
    assert [m["pokemon_id"] for m in miembros] == [1]
