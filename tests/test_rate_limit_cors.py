"""Tests de rate limiting por tipo de endpoint y de CORS (#9)."""

from tests.conftest import PASSWORD


def _login(client):
    return client.post(
        "/api/v1/auth/login", data={"username": "ash", "password": "mala"}
    )


def test_rate_limit_exceeded(client, test_user):
    """Login: 10 por minuto. La 11.ª petición da 429."""
    for _ in range(10):
        assert _login(client).status_code == 401
    r = _login(client)
    assert r.status_code == 429
    # Ni siquiera con la contraseña buena: el límite va antes que la comprobación.
    bueno = client.post(
        "/api/v1/auth/login", data={"username": "ash", "password": PASSWORD}
    )
    assert bueno.status_code == 429


def test_registro_limitado_a_5_por_hora(client):
    for i in range(5):
        r = client.post(
            "/api/v1/auth/register",
            json={"username": f"user{i}", "email": f"u{i}@t.com", "password": PASSWORD},
        )
        assert r.status_code == 201, r.text
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "user9", "email": "u9@t.com", "password": PASSWORD},
    )
    assert r.status_code == 429


def test_pokeapi_limitado_a_30_por_minuto(client, auth_headers):
    for _ in range(30):
        assert client.get("/api/v1/pokemon/25", headers=auth_headers).status_code == 200
    assert client.get("/api/v1/pokemon/25", headers=auth_headers).status_code == 429


def test_autenticados_limitados_a_100_por_minuto(client, auth_headers):
    # El login de auth_headers no cuenta aquí: cada endpoint tiene su contador.
    for _ in range(100):
        assert client.get("/api/v1/teams", headers=auth_headers).status_code == 200
    assert client.get("/api/v1/teams", headers=auth_headers).status_code == 429


def test_los_limites_son_independientes(client, auth_headers):
    for _ in range(30):
        client.get("/api/v1/pokemon/25", headers=auth_headers)
    assert client.get("/api/v1/pokemon/25", headers=auth_headers).status_code == 429
    # Agotar la PokeAPI no bloquea el resto de la API.
    assert client.get("/api/v1/teams", headers=auth_headers).status_code == 200


def test_health_no_tiene_limite(client):
    for _ in range(120):
        assert client.get("/health").status_code == 200


def test_cors_origen_permitido(client):
    r = client.options(
        "/api/v1/teams/1",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "PUT" in r.headers["access-control-allow-methods"]


def test_cors_origen_no_permitido(client):
    r = client.options(
        "/api/v1/teams",
        headers={"Origin": "https://malicioso.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers


# ───────────── IP real detrás de un proxy (Render) ─────────────

from starlette.requests import Request as _Request  # noqa: E402

from app.config import settings  # noqa: E402
from app.limits import ip_cliente  # noqa: E402


def _peticion(xff=None, host="10.0.0.1"):
    cabeceras = [(b"x-forwarded-for", xff.encode())] if xff else []
    return _Request({"type": "http", "headers": cabeceras, "client": (host, 1234)})


def test_sin_proxy_usa_la_ip_de_la_conexion(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy", False)
    # Aunque el cliente mande X-Forwarded-For, no se le hace caso.
    assert ip_cliente(_peticion("1.2.3.4")) == "10.0.0.1"


def test_con_proxy_usa_la_ultima_ip_reenviada(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy", True)
    assert ip_cliente(_peticion("203.0.113.7")) == "203.0.113.7"
    # La primera la puede inventar el cliente; la última la pone el proxy.
    assert ip_cliente(_peticion("6.6.6.6, 203.0.113.7")) == "203.0.113.7"
    # Sin cabecera, la de la conexión.
    assert ip_cliente(_peticion()) == "10.0.0.1"


def test_con_proxy_cada_cliente_tiene_su_limite(client, test_user, monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy", True)
    login = "/api/v1/auth/login"
    mal = {"username": "ash", "password": "Mala12345"}
    for _ in range(10):
        client.post(login, data=mal, headers={"X-Forwarded-For": "198.51.100.1"})
    assert client.post(login, data=mal, headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 429
    # Otro usuario (otra IP real) no queda bloqueado por el primero.
    otro = client.post(login, data=mal, headers={"X-Forwarded-For": "198.51.100.2"})
    assert otro.status_code == 401
    # Inventarse la primera IP no sirve para saltarse el límite.
    falsa = client.post(login, data=mal, headers={"X-Forwarded-For": "9.9.9.9, 198.51.100.1"})
    assert falsa.status_code == 429
