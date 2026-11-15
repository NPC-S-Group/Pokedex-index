"""Tests de la deprecación de la v1 de la Pokédex (mejora de #14)."""

import logging
from datetime import UTC
from email.utils import parsedate_to_datetime

from app.versionado import V1_OBSOLETA_DESDE, V1_RETIRADA

V1 = "/api/v1/pokedex"


def test_listado_v1_avisa_de_la_deprecacion(client, auth_headers):
    r = client.get(V1, headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["deprecation"] == f"@{int(V1_OBSOLETA_DESDE.timestamp())}"
    assert r.headers["link"] == '</api/v2/pokedex>; rel="successor-version"'


def test_sunset_es_una_fecha_http_valida(client, auth_headers):
    r = client.get(V1, headers=auth_headers)
    retirada = parsedate_to_datetime(r.headers["sunset"])
    assert retirada == V1_RETIRADA
    assert r.headers["sunset"].endswith("GMT")


def test_la_retirada_deja_al_menos_6_meses():
    assert (V1_RETIRADA - V1_OBSOLETA_DESDE).days >= 180
    assert V1_OBSOLETA_DESDE.tzinfo is UTC


def test_detalle_v1_apunta_a_su_sucesora(
    client, auth_headers, test_user, add_to_pokedex
):
    (entrada,) = add_to_pokedex(test_user, 25)
    r = client.get(f"{V1}/{entrada.id}", headers=auth_headers)
    assert r.status_code == 200
    assert "deprecation" in r.headers
    assert (
        r.headers["link"] == f'</api/v2/pokedex/{entrada.id}>; rel="successor-version"'
    )


def test_la_v1_sigue_funcionando_igual(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    r = client.get(V1, headers=auth_headers)
    assert r.json()[0]["pokemon_name"] == "pikachu"


def test_rutas_sin_sucesora_no_se_marcan(
    client, auth_headers, test_user, add_to_pokedex
):
    # Escribir, /stats y /export sólo existen en la v1: no están obsoletas.
    (entrada,) = add_to_pokedex(test_user, 25)
    respuestas = [
        client.post(V1, json={"pokemon_id": 1}, headers=auth_headers),
        client.patch(
            f"{V1}/{entrada.id}", json={"favorite": True}, headers=auth_headers
        ),
        client.get(f"{V1}/stats", headers=auth_headers),
        client.get(f"{V1}/export", headers=auth_headers),
        client.get("/api/v2/pokedex", headers=auth_headers),
    ]
    for r in respuestas:
        assert r.status_code < 300, r.text
        assert "deprecation" not in r.headers
        assert "sunset" not in r.headers


def test_swagger_las_muestra_tachadas(client):
    rutas = client.get("/openapi.json").json()["paths"]
    assert rutas["/api/v1/pokedex"]["get"]["deprecated"] is True
    assert rutas["/api/v1/pokedex/{entry_id}"]["get"]["deprecated"] is True
    assert "deprecated" not in rutas["/api/v1/pokedex"]["post"]
    assert "deprecated" not in rutas["/api/v2/pokedex"]["get"]


def test_cada_uso_queda_en_el_log(client, auth_headers, caplog):
    caplog.set_level(logging.INFO, logger="pokedex_api")
    client.get(V1, headers=auth_headers)
    [mensaje] = [
        r.getMessage() for r in caplog.records if r.name == "pokedex_api.versionado"
    ]
    assert (
        mensaje
        == "uso de ruta obsoleta: GET /api/v1/pokedex (sucesora: /api/v2/pokedex)"
    )


def test_cors_deja_leer_las_cabeceras(client, auth_headers):
    r = client.get(V1, headers={**auth_headers, "Origin": "http://localhost:5173"})
    expuestas = r.headers["access-control-expose-headers"].lower()
    for cabecera in ("deprecation", "sunset", "link"):
        assert cabecera in expuestas


def test_despues_del_sunset_responde_410(client, auth_headers, monkeypatch):
    from app import versionado

    monkeypatch.setattr(versionado, "_ahora", lambda: versionado.V1_RETIRADA)
    r = client.get(V1, headers=auth_headers)
    assert r.status_code == 410
    assert "/api/v2/pokedex" in r.json()["detail"]
    assert r.headers["link"] == '</api/v2/pokedex>; rel="successor-version"'
    # La v2 y las rutas sin sucesora siguen funcionando.
    assert client.get("/api/v2/pokedex", headers=auth_headers).status_code == 200
    assert client.get(f"{V1}/stats", headers=auth_headers).status_code == 200


def test_el_dia_antes_del_sunset_aun_funciona(client, auth_headers, monkeypatch):
    from datetime import timedelta

    from app import versionado

    monkeypatch.setattr(
        versionado, "_ahora", lambda: versionado.V1_RETIRADA - timedelta(seconds=1)
    )
    assert client.get(V1, headers=auth_headers).status_code == 200
