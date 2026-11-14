"""Tests de los refresh tokens (bonus del apartado 2.2 del enunciado)."""

from datetime import UTC, datetime, timedelta

from jose import jwt
from sqlmodel import select

from app.auth import create_access_token, create_refresh_token, decode_access_token
from app.config import settings
from app.models import RefreshToken
from tests.conftest import PASSWORD

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


def _login(client, usuario) -> dict:
    r = client.post(LOGIN, data={"username": usuario.username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


def _refrescar(client, refresh_token: str):
    return client.post(REFRESH, json={"refresh_token": refresh_token})


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ───────────────────────────── Login ─────────────────────────────


def test_login_devuelve_access_y_refresh(client, test_user):
    par = _login(client, test_user)
    assert set(par) == {"access_token", "refresh_token", "token_type"}
    assert par["token_type"] == "bearer"
    assert decode_access_token(par["access_token"])["type"] == "access"
    assert decode_access_token(par["refresh_token"])["type"] == "refresh"


def test_access_dura_24_horas_y_refresh_7_dias(client, test_user):
    par = _login(client, test_user)
    access = decode_access_token(par["access_token"])
    refresh = decode_access_token(par["refresh_token"])
    assert access["exp"] - access["iat"] == 24 * 60 * 60
    assert refresh["exp"] - refresh["iat"] == 7 * 24 * 60 * 60


def test_el_refresh_queda_guardado(client, session, test_user):
    par = _login(client, test_user)
    jti = decode_access_token(par["refresh_token"])["jti"]
    registro = session.get(RefreshToken, jti)
    assert registro.user_id == test_user.id
    assert registro.revoked_at is None


# ───────────────────────────── Refresh ─────────────────────────────


def test_refresh_devuelve_un_par_nuevo_que_funciona(client, test_user):
    par = _login(client, test_user)
    r = _refrescar(client, par["refresh_token"])
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert nuevo["refresh_token"] != par["refresh_token"]
    me = client.get(ME, headers=_bearer(nuevo["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == test_user.username


def test_rotacion_el_refresh_usado_ya_no_vale(client, test_user):
    par = _login(client, test_user)
    assert _refrescar(client, par["refresh_token"]).status_code == 200
    assert _refrescar(client, par["refresh_token"]).status_code == 401


def test_reutilizar_un_refresh_anula_todos_los_del_usuario(client, test_user):
    # El ladrón y el usuario tienen el mismo refresh: el primero que lo usa obtiene
    # un par nuevo; cuando el otro lo reutiliza, se anula también ese par nuevo.
    robado = _login(client, test_user)["refresh_token"]
    del_ladron = _refrescar(client, robado).json()["refresh_token"]
    otro_dispositivo = _login(client, test_user)["refresh_token"]

    assert _refrescar(client, robado).status_code == 401
    assert _refrescar(client, del_ladron).status_code == 401
    assert _refrescar(client, otro_dispositivo).status_code == 401


def test_la_reutilizacion_no_afecta_a_otros_usuarios(client, test_user, other_user):
    robado = _login(client, test_user)["refresh_token"]
    de_otro = _login(client, other_user)["refresh_token"]
    _refrescar(client, robado)
    _refrescar(client, robado)  # reutilización: anula los de test_user
    assert _refrescar(client, de_otro).status_code == 200


def test_varias_sesiones_son_independientes(client, test_user):
    movil = _login(client, test_user)["refresh_token"]
    portatil = _login(client, test_user)["refresh_token"]
    assert _refrescar(client, movil).status_code == 200
    assert _refrescar(client, portatil).status_code == 200


def test_un_access_token_no_sirve_para_refrescar(client, test_user):
    par = _login(client, test_user)
    assert _refrescar(client, par["access_token"]).status_code == 401


def test_un_refresh_token_no_sirve_para_entrar(client, test_user):
    par = _login(client, test_user)
    assert client.get(ME, headers=_bearer(par["refresh_token"])).status_code == 401
    r = client.get("/api/v1/pokedex", headers=_bearer(par["refresh_token"]))
    assert r.status_code == 401


def test_refresh_caducado(client, session, test_user):
    pasado = datetime.now(UTC) - timedelta(minutes=1)
    token = jwt.encode(
        {
            "sub": "ash",
            "user_id": test_user.id,
            "type": "refresh",
            "jti": "x" * 32,
            "exp": pasado,
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    session.add(RefreshToken(jti="x" * 32, user_id=test_user.id, expires_at=pasado))
    session.commit()
    assert _refrescar(client, token).status_code == 401


def test_refresh_firmado_con_otra_clave(client, test_user):
    token = jwt.encode(
        {"user_id": test_user.id, "type": "refresh", "jti": "y" * 32},
        "otra-clave",
        algorithm=settings.algorithm,
    )
    assert _refrescar(client, token).status_code == 401


def test_refresh_bien_firmado_pero_no_emitido(client, test_user):
    # Firmado con nuestra clave pero sin registro en la BD: no lo hemos dado nosotros.
    token, _, _ = create_refresh_token(test_user.username, test_user.id)
    assert _refrescar(client, token).status_code == 401


def test_refresh_con_user_id_cambiado(client, session, test_user, other_user):
    token, jti, caduca = create_refresh_token(test_user.username, test_user.id)
    session.add(RefreshToken(jti=jti, user_id=other_user.id, expires_at=caduca))
    session.commit()
    assert _refrescar(client, token).status_code == 401


def test_refresh_de_usuario_desactivado(client, session, test_user):
    par = _login(client, test_user)
    test_user.is_active = False
    session.add(test_user)
    session.commit()
    assert _refrescar(client, par["refresh_token"]).status_code == 401


def test_refresh_de_usuario_borrado(client, session, test_user):
    par = _login(client, test_user)
    session.delete(test_user)
    session.commit()
    assert _refrescar(client, par["refresh_token"]).status_code == 401


def test_refresh_basura_o_vacio(client):
    assert _refrescar(client, "basura").status_code == 401
    assert client.post(REFRESH, json={"refresh_token": ""}).status_code == 422
    assert client.post(REFRESH, json={}).status_code == 422


# ───────────────────────────── Logout ─────────────────────────────


def test_logout_anula_el_refresh(client, session, test_user):
    par = _login(client, test_user)
    r = client.post(LOGOUT, json={"refresh_token": par["refresh_token"]})
    assert r.status_code == 204
    assert _refrescar(client, par["refresh_token"]).status_code == 401
    jti = decode_access_token(par["refresh_token"])["jti"]
    assert session.get(RefreshToken, jti).revoked_at is not None


def test_logout_solo_anula_esa_sesion(client, test_user):
    movil = _login(client, test_user)["refresh_token"]
    portatil = _login(client, test_user)["refresh_token"]
    client.post(LOGOUT, json={"refresh_token": movil})
    assert _refrescar(client, portatil).status_code == 200


def test_logout_responde_204_aunque_el_token_no_valga(client, test_user):
    # Siempre 204: el logout no sirve para averiguar qué tokens existen.
    par = _login(client, test_user)
    for token in (
        "basura",
        par["access_token"],
        par["refresh_token"],
        par["refresh_token"],
    ):
        assert client.post(LOGOUT, json={"refresh_token": token}).status_code == 204


def test_el_access_token_sigue_valiendo_tras_el_logout(client, test_user):
    # Limitación documentada: el access token no se puede anular, caduca en 24 h.
    par = _login(client, test_user)
    client.post(LOGOUT, json={"refresh_token": par["refresh_token"]})
    assert client.get(ME, headers=_bearer(par["access_token"])).status_code == 200


# ───────────────────────────── Compatibilidad y límites ─────────────────────────────


def test_access_token_sin_type_sigue_valiendo(client, test_user):
    # Tokens emitidos antes de esta mejora, sin el claim «type»: siguen valiendo hasta caducar.
    token = jwt.encode(
        {
            "sub": "ash",
            "user_id": test_user.id,
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    assert client.get(ME, headers=_bearer(token)).status_code == 200


def test_create_access_token_lleva_type_access():
    assert decode_access_token(create_access_token("ash", 1))["type"] == "access"


def test_cada_refresh_tiene_su_jti(client, session, test_user):
    _login(client, test_user)
    _login(client, test_user)
    jtis = session.exec(select(RefreshToken.jti)).all()
    assert len(jtis) == len(set(jtis)) == 2


def test_refresh_limitado_a_10_por_minuto(client):
    for _ in range(10):
        assert _refrescar(client, "basura").status_code == 401
    assert _refrescar(client, "basura").status_code == 429


def test_logout_limitado_a_10_por_minuto(client):
    for _ in range(10):
        client.post(LOGOUT, json={"refresh_token": "basura"})
    assert client.post(LOGOUT, json={"refresh_token": "basura"}).status_code == 429


def test_aparecen_en_swagger(client):
    rutas = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/auth/refresh" in rutas
    assert "/api/v1/auth/logout" in rutas
