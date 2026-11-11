"""Tests del equipo en PDF (#13)."""

import base64
import re

import pytest

from app.services.equipo_pdf import estadisticas_combinadas, generar_pdf_equipo
from tests.conftest import PokeAPIFalsa

URL = "/api/v1/teams"
# PNG de 1x1 píxel, para probar la ficha con imagen sin salir a internet.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _paginas(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf))


def _equipo(client, headers, ids):
    r = client.post(
        URL,
        json={"name": "Equipo Elite", "description": "Mi equipo", "pokemon_ids": ids},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_exportar_equipo(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, 1, 4)
    team_id = _equipo(client, auth_headers, [25, 1, 4])
    r = client.get(f"{URL}/{team_id}/export", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert f'filename="equipo-{team_id}.pdf"' in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")
    # Portada + una ficha por Pokémon.
    assert _paginas(r.content) == 4


def test_exportar_con_imagenes(client, auth_headers, test_user, add_to_pokedex, monkeypatch):
    async def con_imagen(self, url):
        return PNG

    monkeypatch.setattr(PokeAPIFalsa, "descargar_imagen", con_imagen)
    add_to_pokedex(test_user, 25)
    team_id = _equipo(client, auth_headers, [25])
    r = client.get(f"{URL}/{team_id}/export", headers=auth_headers)
    assert r.status_code == 200
    assert _paginas(r.content) == 2


def test_exportar_equipo_de_otro(client, auth_headers, other_headers, other_user, add_to_pokedex):
    add_to_pokedex(other_user, 25)
    team_id = _equipo(client, other_headers, [25])
    assert client.get(f"{URL}/{team_id}/export", headers=auth_headers).status_code == 404


def test_exportar_inexistente_y_sin_token(client, auth_headers):
    assert client.get(f"{URL}/999/export", headers=auth_headers).status_code == 404
    assert client.get(f"{URL}/1/export").status_code == 401


def test_estadisticas_combinadas():
    pokemons = [
        {"types": ["fire"], "stats": {"hp": 40, "attack": 60, "speed": 100}},
        {"types": ["fire", "flying"], "stats": {"hp": 80, "attack": 100, "speed": None}},
    ]
    s = estadisticas_combinadas(pokemons)
    assert s["total"]["hp"] == 120
    assert s["media"]["hp"] == 60.0
    assert s["media"]["attack"] == 80.0
    # Una estadística que falta no cuenta para la media.
    assert s["media"]["speed"] == 100.0
    assert s["total"]["defense"] == 0 and s["media"]["defense"] == 0.0
    assert s["total_equipo"] == 120 + 160 + 100
    assert s["tipos"] == {"fire": 2, "flying": 1}


def test_estadisticas_equipo_vacio():
    s = estadisticas_combinadas([])
    assert s["total_equipo"] == 0 and s["tipos"] == {}


@pytest.mark.parametrize("descripcion", [None, "Texto largo " * 30])
def test_generar_pdf_equipo(descripcion):
    miembros = [
        {
            "position": i,
            "nickname": "Rayo" if i == 1 else None,
            "pokemon": {
                "id": pid,
                "name": nombre,
                "types": tipos,
                "stats": {"hp": 50, "attack": 60, "defense": 70, "speed": 80},
            },
            "imagen": None,
        }
        for i, (pid, nombre, tipos) in enumerate(
            [(25, "pikachu", ["electric"]), (6, "charizard", ["fire", "flying"]),
             (130, "gyarados", ["water", "flying"]), (94, "gengar", ["ghost", "poison"]),
             (143, "snorlax", ["normal"]), (149, "dragonite", ["dragon", "flying"])],
            start=1,
        )
    ]
    pdf = generar_pdf_equipo("Equipo Elite", descripcion, miembros)
    assert pdf.startswith(b"%PDF")
    assert _paginas(pdf) == 7
