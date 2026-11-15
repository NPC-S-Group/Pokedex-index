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
