"""Tests de los arreglos de la revisión de seguridad.

IP real detrás del proxy, límite de login por cuenta, cabeceras de seguridad y
limpieza de refresh tokens.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import select

from app import limits
from app.models import RefreshToken, ahora
from app.routers.auth import borrar_refresh_caducados
from tests.conftest import PASSWORD

LOGIN = "/api/v1/auth/login"


def login(client, username="ash", password=PASSWORD):
    return client.post(LOGIN, data={"username": username, "password": password})


# Contraseñas de más de 72 bytes: tests/test_auth.py. SECRET_KEY: tests/test_config.py.


# --- IP real detrás del proxy ------------------------------------------------------


def peticion(xff: str | None, ip_conexion="10.0.0.1"):
    cabeceras = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(headers=cabeceras, client=SimpleNamespace(host=ip_conexion))


@pytest.mark.parametrize(
    "saltos, xff, esperada",
    [
        (0, "1.1.1.1", "10.0.0.1"),  # sin proxy: se ignora la cabecera
        (1, "1.1.1.1", "1.1.1.1"),
        # El cliente se inventa «6.6.6.6»: con 1 salto se usa la que puso Render.
        (1, "6.6.6.6, 1.1.1.1", "1.1.1.1"),
        (2, "6.6.6.6, 1.1.1.1, 172.16.0.5", "1.1.1.1"),
        (1, None, "10.0.0.1"),  # sin cabecera: la de la conexión
        (2, "1.1.1.1", "10.0.0.1"),  # menos entradas que saltos: no se fía
    ],
)
def test_ip_cliente(monkeypatch, saltos, xff, esperada):
    monkeypatch.setattr(limits.settings, "trusted_proxy_hops", saltos)
    assert limits.ip_cliente(peticion(xff)) == esperada


def test_detras_del_proxy_cada_ip_tiene_su_limite(client, monkeypatch):
    # Antes, todos llegaban con la IP del proxy y compartían los 10 logins/minuto.
    monkeypatch.setattr(limits.settings, "trusted_proxy_hops", 1)
    for i in range(10):
        r = client.post(
            LOGIN,
            data={"username": f"u{i}", "password": "mala"},
            headers={"X-Forwarded-For": "1.1.1.1"},
        )
        assert r.status_code == 401
    bloqueada = {"X-Forwarded-For": "1.1.1.1"}
    otra = {"X-Forwarded-For": "2.2.2.2"}
    datos = {"username": "nadie", "password": "mala"}
    assert client.post(LOGIN, data=datos, headers=bloqueada).status_code == 429
    assert client.post(LOGIN, data=datos, headers=otra).status_code == 401


# --- Límite de login por cuenta ---------------------------------------------------


def test_cinco_fallos_bloquean_la_cuenta(client, test_user):
    for _ in range(5):
        assert login(client, password="Mala12345").status_code == 401
    # Ni con la contraseña buena: la cuenta está bloqueada 15 minutos.
    r = login(client)
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "900"


def test_el_bloqueo_no_distingue_mayusculas(client, test_user):
    for nombre in ["ash", "ASH", "Ash", " ash ", "aSh"]:
        login(client, nombre, "Mala12345")
    assert login(client).status_code == 429


def test_el_bloqueo_no_afecta_a_otras_cuentas(client, test_user, other_user):
    for _ in range(5):
        login(client, password="Mala12345")
    assert login(client, "gary").status_code == 200


def test_un_login_correcto_pone_el_contador_a_cero(client, test_user):
    for _ in range(4):
        login(client, password="Mala12345")
    assert login(client).status_code == 200
    for _ in range(4):
        assert login(client, password="Mala12345").status_code == 401
    assert login(client).status_code == 200


def test_usuarios_que_no_existen_tambien_se_bloquean(client):
    # Si no, el 429 delataría qué nombres existen.
    for _ in range(5):
        assert login(client, "fantasma", "x").status_code == 401
    assert login(client, "fantasma", "x").status_code == 429


# --- Cabeceras de seguridad ---------------------------------------------------------


def test_cabeceras_en_la_api(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Content-Security-Policy"].startswith("default-src 'none'")


def test_hsts_solo_por_https(client):
    # Por HTTP (local) no se manda HSTS…
    assert "Strict-Transport-Security" not in client.get("/health").headers
    # …y detrás de un proxy HTTPS (Render) sí.
    r = client.get("/health", headers={"X-Forwarded-Proto": "https"})
    assert r.headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_docs_sin_csp_para_que_swagger_cargue(client):
    r = client.get("/docs")
    assert r.status_code == 200
    assert "Content-Security-Policy" not in r.headers
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_las_respuestas_de_auth_no_se_cachean(client, test_user):
    assert login(client).headers["Cache-Control"] == "no-store"
    assert "Cache-Control" not in client.get("/health").headers


def test_los_errores_tambien_llevan_cabeceras(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.headers["X-Frame-Options"] == "DENY"


# --- Limpieza de refresh tokens caducados -----------------------------------------


def _token(session, jti, user_id, dias):
    session.add(
        RefreshToken(
            jti=jti, user_id=user_id, expires_at=ahora() + timedelta(days=dias)
        )
    )
    session.commit()


def jtis(session) -> set[str]:
    return {t.jti for t in session.exec(select(RefreshToken))}


def test_borra_solo_los_caducados(session, test_user):
    _token(session, "viejo", test_user.id, -1)
    _token(session, "vivo", test_user.id, 3)
    assert borrar_refresh_caducados(session) == 1
    assert jtis(session) == {"vivo"}


def test_al_hacer_login_se_limpian_los_del_usuario(
    client, session, test_user, other_user
):
    _token(session, "viejo-ash", test_user.id, -1)
    _token(session, "viejo-gary", other_user.id, -1)
    assert login(client).status_code == 200
    quedan = jtis(session)
    assert "viejo-ash" not in quedan
    assert "viejo-gary" in quedan  # los de otros, al arrancar la app
    assert len(quedan) == 2  # el de gary y el nuevo de ash
