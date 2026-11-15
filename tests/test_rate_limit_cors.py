"""Tests de rate limiting por tipo de endpoint y de CORS (#9)."""

from tests.conftest import PASSWORD


def _login(client):
    return client.post(
        "/api/v1/auth/login", data={"username": "ash", "password": "mala"}
    )


def test_rate_limit_exceeded(client, test_user):
    """Login: 10 por minuto y por IP. La 11.ª petición da 429.

    Cada intento usa un nombre distinto para no tocar el límite POR CUENTA (5),
    que se prueba aparte en test_seguridad.py.
    """
    for i in range(10):
        r = client.post(
            "/api/v1/auth/login", data={"username": f"otro{i}", "password": "mala"}
        )
        assert r.status_code == 401
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
# Los casos de ip_cliente con 0, 1 y 2 proxies están en tests/test_seguridad.py.

from app.config import settings


def test_con_proxy_cada_cliente_tiene_su_limite(client, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    login = "/api/v1/auth/login"

    def intento(i, xff):
        # Un usuario distinto cada vez: así salta el límite por IP, no el de cuenta.
        datos = {"username": f"u{i}", "password": "Mala12345"}
        return client.post(login, data=datos, headers={"X-Forwarded-For": xff})

    for i in range(10):
        intento(i, "198.51.100.1")
    assert intento(10, "198.51.100.1").status_code == 429
    # Otro usuario (otra IP real) no queda bloqueado por el primero.
    assert intento(11, "198.51.100.2").status_code == 401
    # Inventarse la primera IP no sirve para saltarse el límite.
    assert intento(12, "9.9.9.9, 198.51.100.1").status_code == 429
