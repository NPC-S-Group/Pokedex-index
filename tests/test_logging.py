"""Tests del logging (#10): peticiones, auth, validación y 429."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_pokeapi_service
from app.main import app
from tests.conftest import PASSWORD

LOGIN = "/api/v1/auth/login"
REGISTRO = "/api/v1/auth/register"


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.DEBUG, logger="pokedex_api")
    return caplog


def mensajes(caplog, logger: str, nivel: int | None = None) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == logger and (nivel is None or r.levelno == nivel)
    ]


# --- Peticiones ---------------------------------------------------------------


def test_registra_cada_peticion(client, logs):
    client.get("/health")
    [linea] = mensajes(logs, "pokedex_api.peticiones")
    assert "GET /health → 200" in linea
    assert "usuario=anónimo" in linea
    assert "ms)" in linea


def test_registra_el_usuario_del_token(client, auth_headers, logs):
    logs.clear()
    client.get("/api/v1/teams", headers=auth_headers)
    [linea] = mensajes(logs, "pokedex_api.peticiones")
    assert "GET /api/v1/teams → 200" in linea
    assert "usuario='ash'" in linea


def test_token_no_valido_aparece_como_tal(client, logs):
    client.get("/api/v1/teams", headers={"Authorization": "Bearer inventado"})
    [linea] = mensajes(logs, "pokedex_api.peticiones")
    assert "→ 401" in linea
    assert "usuario=token-no-válido" in linea


@pytest.mark.parametrize(
    "ruta, nivel",
    [("/health", logging.INFO), ("/api/v1/teams", logging.WARNING)],  # 200 y 401
)
def test_el_nivel_depende_del_codigo(client, logs, ruta, nivel):
    client.get(ruta)
    [registro] = [r for r in logs.records if r.name == "pokedex_api.peticiones"]
    assert registro.levelno == nivel


def test_no_registra_la_query_string(client, auth_headers, logs):
    logs.clear()
    client.get("/api/v1/teams?secreto=no-debe-salir", headers=auth_headers)
    nuestros = [
        r.getMessage() for r in logs.records if r.name.startswith("pokedex_api")
    ]
    assert nuestros
    assert not any("no-debe-salir" in m for m in nuestros)


def test_devuelve_un_id_de_peticion(client, logs):
    r = client.get("/health")
    id_peticion = r.headers["X-Request-ID"]
    assert len(id_peticion) == 12
    assert f"[{id_peticion}]" in logs.text


def test_reutiliza_el_id_del_cliente_si_es_valido(client):
    r = client.get("/health", headers={"X-Request-ID": "front-1234"})
    assert r.headers["X-Request-ID"] == "front-1234"


def test_ignora_un_id_del_cliente_con_basura(client, logs):
    r = client.get("/health", headers={"X-Request-ID": "x\tFALSO INFO hackeado"})
    assert r.headers["X-Request-ID"] != "x\tFALSO INFO hackeado"
    assert "hackeado" not in logs.text


def test_registra_los_errores_no_controlados(client, auth_headers, logs):
    class PokeAPIRota:
        async def get_pokemon(self, identificador):
            raise RuntimeError("bug simulado")

    app.dependency_overrides[get_pokeapi_service] = PokeAPIRota
    cliente = TestClient(app, raise_server_exceptions=False)
    r = cliente.get("/api/v1/pokemon/25", headers=auth_headers)

    assert r.status_code == 500
    [registro] = [
        r
        for r in logs.records
        if r.name == "pokedex_api.peticiones" and r.levelno == logging.ERROR
    ]
    assert "GET /api/v1/pokemon/25 → error no controlado" in registro.getMessage()
    assert registro.exc_info is not None  # con la traza, para poder depurarlo


# --- Autenticación -------------------------------------------------------------


def test_registra_el_registro_de_usuarios(client, logs):
    datos = {"username": "misty", "email": "misty@test.com", "password": PASSWORD}
    client.post(REGISTRO, json=datos)
    client.post(REGISTRO, json=datos)
    auth = mensajes(logs, "pokedex_api.auth")
    assert any("usuario registrado: 'misty'" in m for m in auth)
    assert any("registro rechazado" in m and "'misty'" in m for m in auth)


def test_registra_login_correcto_y_fallido(client, test_user, logs):
    client.post(LOGIN, data={"username": "ash", "password": PASSWORD})
    client.post(LOGIN, data={"username": "ash", "password": "Mala12345"})
    assert any("login correcto: 'ash'" in m for m in mensajes(logs, "pokedex_api.auth"))
    assert mensajes(logs, "pokedex_api.auth", logging.WARNING) == [
        "login fallido para 'ash'"
    ]


def test_nunca_registra_contrasenas_ni_tokens(client, test_user, logs):
    r = client.post(LOGIN, data={"username": "ash", "password": PASSWORD})
    token = r.json()["access_token"]
    client.get("/api/v1/teams", headers={"Authorization": f"Bearer {token}"})
    client.post(LOGIN, data={"username": "ash", "password": "OtraClave777"})
    assert PASSWORD not in logs.text
    assert "OtraClave777" not in logs.text
    assert token not in logs.text


def test_un_nombre_con_salto_de_linea_no_falsea_el_log(client, logs):
    client.post(LOGIN, data={"username": "ash\nINFO login correcto", "password": "x"})
    [mensaje] = mensajes(logs, "pokedex_api.auth", logging.WARNING)
    assert "\n" not in mensaje
    assert "\\n" in mensaje


def test_registra_tokens_no_validos(client, logs):
    client.get("/api/v1/teams", headers={"Authorization": "Bearer inventado"})
    assert mensajes(logs, "pokedex_api.auth", logging.WARNING) == [
        "token no válido o caducado"
    ]


def test_registra_tokens_de_usuarios_borrados(client, session, test_user, logs):
    token = client.post(LOGIN, data={"username": "ash", "password": PASSWORD}).json()[
        "access_token"
    ]
    session.delete(test_user)
    session.commit()
    client.get("/api/v1/teams", headers={"Authorization": f"Bearer {token}"})
    assert any(
        "usuario inexistente o inactivo" in m
        for m in mensajes(logs, "pokedex_api.auth", logging.WARNING)
    )


# --- Validación (422) ------------------------------------------------------------


def test_registra_que_campos_fallan(client, logs):
    r = client.post(REGISTRO, json={"username": "brock"})
    assert r.status_code == 422
    [mensaje] = mensajes(logs, "pokedex_api.validacion", logging.WARNING)
    assert "POST /api/v1/auth/register → 422" in mensaje
    assert "body.email" in mensaje
    assert "body.password" in mensaje


def test_la_validacion_no_registra_los_valores(client, logs):
    r = client.post(
        REGISTRO,
        json={"username": "brock", "email": "no-es-email", "password": "sinnumeros"},
    )
    assert r.status_code == 422
    assert "sinnumeros" not in logs.text
    assert "no-es-email" not in logs.text


def test_la_respuesta_422_no_cambia(client):
    r = client.post(REGISTRO, json={"username": "brock"})
    campos = {tuple(e["loc"]) for e in r.json()["detail"]}
    assert ("body", "email") in campos


# --- Límites (429) ---------------------------------------------------------------


def test_registra_el_429(client, test_user, logs):
    # Un nombre distinto cada vez: así salta el límite por IP y no el de la cuenta.
    for i in range(11):
        r = client.post(LOGIN, data={"username": f"otro{i}", "password": "Mala12345"})
    assert r.status_code == 429
    [mensaje] = mensajes(logs, "pokedex_api.limites", logging.WARNING)
    assert "POST /api/v1/auth/login → 429" in mensaje
    assert "10 per 1 minute" in mensaje
    assert "ip=testclient" in mensaje


def test_el_429_registra_el_usuario(client, auth_headers, logs):
    for _ in range(31):
        client.get("/api/v1/pokemon/25", headers=auth_headers)
    [mensaje] = mensajes(logs, "pokedex_api.limites")
    assert "usuario='ash'" in mensaje


# --- Configuración ---------------------------------------------------------------


def test_nivel_de_log_configurable(monkeypatch):
    from app.logs import configurar_logging

    configurar_logging("WARNING")
    try:
        assert logging.getLogger("pokedex_api").level == logging.WARNING
    finally:
        configurar_logging("INFO")
