"""Tests de registro, login JWT y usuario actual (#4)."""

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt
from sqlmodel import select

from app.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.models import User
from tests.conftest import PASSWORD

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def _registrar(client, username="misty", email="misty@test.com", password=PASSWORD):
    return client.post(
        REGISTER, json={"username": username, "email": email, "password": password}
    )


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ───────────────────────────── Registro ─────────────────────────────


def test_registro_correcto(client):
    r = _registrar(client)
    assert r.status_code == 201, r.text
    datos = r.json()
    assert datos["username"] == "misty"
    assert datos["email"] == "misty@test.com"
    assert isinstance(datos["id"], int)
    assert "created_at" in datos


def test_registro_no_devuelve_la_contrasena(client):
    datos = _registrar(client).json()
    assert "password" not in datos
    assert "hashed_password" not in datos


def test_registro_guarda_hash_bcrypt_y_no_texto_plano(client, session):
    _registrar(client)
    usuario = session.exec(select(User).where(User.username == "misty")).one()
    assert usuario.hashed_password != PASSWORD
    assert usuario.hashed_password.startswith("$2")  # prefijo de bcrypt
    assert verify_password(PASSWORD, usuario.hashed_password)


def test_registro_usuario_repetido(client, test_user):
    r = _registrar(client, username=test_user.username, email="otro@test.com")
    assert r.status_code == 409


def test_registro_email_repetido(client, test_user):
    r = _registrar(client, username="otro", email=test_user.email)
    assert r.status_code == 409


def test_registro_contrasena_corta(client):
    assert _registrar(client, password="Ab1").status_code == 422


def test_registro_contrasena_sin_mayuscula(client):
    assert _registrar(client, password="secreta123").status_code == 422


def test_registro_contrasena_sin_numero(client):
    assert _registrar(client, password="SecretaSecreta").status_code == 422


def test_registro_email_invalido(client):
    assert _registrar(client, email="no-es-un-email").status_code == 422


def test_registro_username_corto(client):
    assert _registrar(client, username="ab").status_code == 422


def test_registro_sin_campos(client):
    assert client.post(REGISTER, json={}).status_code == 422


# ───────────────────────────── Login ─────────────────────────────


def test_login_correcto_devuelve_token(client, test_user):
    r = client.post(LOGIN, data={"username": test_user.username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["token_type"] == "bearer"
    payload = decode_access_token(datos["access_token"])
    assert payload["sub"] == test_user.username
    assert payload["user_id"] == test_user.id


def test_login_tras_registrarse(client):
    _registrar(client)
    r = client.post(LOGIN, data={"username": "misty", "password": PASSWORD})
    assert r.status_code == 200


def test_login_contrasena_mala(client, test_user):
    r = client.post(
        LOGIN, data={"username": test_user.username, "password": "Mala1234"}
    )
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_login_usuario_inexistente_mismo_mensaje(client, test_user):
    # No debe revelar si el usuario existe: mismo código y mismo mensaje.
    mala = client.post(
        LOGIN, data={"username": test_user.username, "password": "Mala1234"}
    )
    no_existe = client.post(LOGIN, data={"username": "nadie", "password": "Mala1234"})
    assert no_existe.status_code == 401
    assert no_existe.json() == mala.json()


def test_login_sin_formulario(client):
    assert client.post(LOGIN).status_code == 422


# ───────────────────────────── Usuario actual ─────────────────────────────


def test_me_devuelve_el_usuario_del_token(client, auth_headers, test_user):
    r = client.get(ME, headers=auth_headers)
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["id"] == test_user.id
    assert datos["username"] == test_user.username
    assert "hashed_password" not in datos


def test_me_sin_token(client):
    r = client.get(ME)
    assert r.status_code == 401


def test_me_token_inventado(client):
    assert client.get(ME, headers=_bearer("esto.no.vale")).status_code == 401


def test_me_token_firmado_con_otra_clave(client, test_user):
    token = jwt.encode(
        {"sub": test_user.username, "user_id": test_user.id},
        "otra-clave",
        algorithm=settings.algorithm,
    )
    assert client.get(ME, headers=_bearer(token)).status_code == 401


def test_me_token_caducado(client, test_user):
    pasado = datetime.now(UTC) - timedelta(minutes=5)
    token = jwt.encode(
        {"sub": test_user.username, "user_id": test_user.id, "exp": pasado},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    assert client.get(ME, headers=_bearer(token)).status_code == 401


def test_me_token_sin_user_id(client, test_user):
    token = jwt.encode(
        {"sub": test_user.username}, settings.secret_key, algorithm=settings.algorithm
    )
    assert client.get(ME, headers=_bearer(token)).status_code == 401


def test_me_usuario_borrado(client, session, test_user):
    token = create_access_token(test_user.username, test_user.id)
    session.delete(test_user)
    session.commit()
    assert client.get(ME, headers=_bearer(token)).status_code == 401


def test_me_usuario_desactivado(client, session, test_user, auth_headers):
    test_user.is_active = False
    session.add(test_user)
    session.commit()
    assert client.get(ME, headers=auth_headers).status_code == 401


def test_rutas_protegidas_piden_token(client):
    for url in ("/api/v1/pokedex", "/api/v1/teams", "/api/v1/pokemon/25"):
        assert client.get(url).status_code == 401, url


# ───────────────────────────── Funciones de app/auth.py ─────────────────────────────


def test_hash_es_distinto_cada_vez():
    # bcrypt usa sal aleatoria: mismo texto, hash distinto.
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_password():
    hashed = hash_password(PASSWORD)
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("Otra1234", hashed)


def test_token_caduca_segun_configuracion():
    payload = decode_access_token(create_access_token("ash", 1))
    duracion = payload["exp"] - payload["iat"]
    assert duracion == settings.access_token_expire_minutes * 60


def test_decode_token_invalido_devuelve_none():
    assert decode_access_token("basura") is None


def test_registro_simultaneo_lo_resuelve_la_bd(client, session, monkeypatch):
    # Simula que otro registro con el mismo nombre se cuela entre la comprobación
    # y el commit: la restricción UNIQUE salta y la API responde 409, no 500.
    from sqlalchemy.exc import IntegrityError

    def commit_que_falla():
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(session, "commit", commit_que_falla)
    assert _registrar(client).status_code == 409


# ───────────────────────────── Login sin pistas ─────────────────────────────


def _intento(client, username, password):
    return client.post(LOGIN, data={"username": username, "password": password})


def test_login_mismo_error_sea_cual_sea_el_fallo(client, session, test_user):
    # Ni el código, ni el mensaje, ni las cabeceras dicen si falla el usuario o la clave.
    inactivo = User(
        username="misty",
        email="misty@test.com",
        hashed_password=hash_password(PASSWORD),
        is_active=False,
    )
    session.add(inactivo)
    session.commit()
    casos = {
        "usuario no existe": ("nadie", PASSWORD),
        "contraseña mala": (test_user.username, "Mala12345"),
        "los dos mal": ("nadie", "Mala12345"),
        "cuenta desactivada": ("misty", PASSWORD),
    }
    respuestas = {nombre: _intento(client, *datos) for nombre, datos in casos.items()}
    for nombre, r in respuestas.items():
        assert r.status_code == 401, nombre
        assert r.json() == {"detail": "Usuario o contraseña incorrectos"}, nombre
        assert r.headers["www-authenticate"] == "Bearer", nombre
        assert "access_token" not in r.text, nombre


def test_login_ejecuta_bcrypt_aunque_el_usuario_no_exista(
    client, test_user, monkeypatch
):
    # Si no se comprobara la clave cuando el usuario no existe, la respuesta llegaría
    # mucho antes y el tiempo delataría qué usuarios hay (timing attack).
    from app.routers import auth as router_auth

    llamadas = []
    original = router_auth.verify_password

    def espia(password, hashed):
        llamadas.append(hashed)
        return original(password, hashed)

    monkeypatch.setattr(router_auth, "verify_password", espia)
    _intento(client, "nadie", PASSWORD)
    _intento(client, test_user.username, "Mala12345")
    assert len(llamadas) == 2
    assert llamadas[0] == router_auth._HASH_FALSO
    assert llamadas[1] == test_user.hashed_password


def test_login_tarda_lo_mismo_exista_o_no_el_usuario(client, test_user):
    # Antes: ~9 ms si el usuario no existía y ~250 ms si existía. Margen amplio para
    # que no falle por ruido en el CI: solo tiene que pillar diferencias de 3 veces.
    import statistics
    import time

    def mediana(username):
        tiempos = []
        for _ in range(5):
            inicio = time.perf_counter()
            _intento(client, username, "Mala12345")
            tiempos.append(time.perf_counter() - inicio)
        return statistics.median(tiempos)

    no_existe, existe = mediana("nadie"), mediana(test_user.username)
    assert 1 / 3 < no_existe / existe < 3, (no_existe, existe)


# ───────────────────── Mayúsculas y nombres limpios (mejoras) ─────────────────────


def test_email_sin_distinguir_mayusculas(client):
    r = _registrar(client, username="misty", email="  Misty@Test.COM ")
    assert r.status_code == 201, r.text
    # Se guarda en minúsculas y sin espacios.
    assert r.json()["email"] == "misty@test.com"
    # El mismo correo escrito de otra forma ya existe.
    assert _registrar(client, username="otra", email="MISTY@test.com").status_code == 409


def test_usuario_sin_distinguir_mayusculas(client):
    assert _registrar(client, username="Misty").status_code == 201
    r = _registrar(client, username="misty", email="otra@test.com")
    assert r.status_code == 409
    r = _registrar(client, username="MISTY", email="otra2@test.com")
    assert r.status_code == 409


def test_login_sin_distinguir_mayusculas(client):
    r = _registrar(client, username="Misty")
    assert r.json()["username"] == "Misty"  # se muestra tal y como se escribió
    for escrito in ("Misty", "misty", "MISTY", "mIsTy", " misty "):
        r = client.post(LOGIN, data={"username": escrito, "password": PASSWORD})
        assert r.status_code == 200, escrito
        me = client.get(ME, headers=_bearer(r.json()["access_token"]))
        assert me.json()["username"] == "Misty"


def test_indice_unico_sin_mayusculas_en_la_bd(session, test_user):
    # Aunque alguien se salte la comprobación de la API, la BD no deja duplicar.
    from sqlalchemy.exc import IntegrityError

    session.add(
        User(
            username=test_user.username.upper(),
            email="otro@test.com",
            hashed_password="x",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


@pytest.mark.parametrize(
    "username",
    ["   ", "  ab  ", "a b", "a\tb", "ab\nc", "ash!", "ñandú"],
)
def test_usuario_con_espacios_o_signos_raros(client, username):
    assert _registrar(client, username=username).status_code == 422


def test_usuario_con_espacios_en_los_extremos_se_limpia(client):
    r = _registrar(client, username="  misty_92  ")
    assert r.status_code == 201
    assert r.json()["username"] == "misty_92"
