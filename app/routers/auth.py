"""Registro, login, refresh tokens, logout y usuario actual."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlmodel import func, or_, select, update

from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.dependencies import CurrentUser, SessionDep
from app.limits import LIMITE_AUTENTICADO, LIMITE_LOGIN, LIMITE_REGISTRO, limiter
from app.models import (
    RefreshRequest,
    RefreshToken,
    TokenPair,
    User,
    UserCreate,
    UserRead,
    ahora,
)

# Los nombres van con %r: escapa saltos de línea y nadie puede falsear líneas del log.
logger = logging.getLogger("pokedex_api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# Mensaje único para cualquier fallo del login: no dice si falla el usuario o la clave.
LOGIN_INCORRECTO = "Usuario o contraseña incorrectos"

# Hash de una contraseña que nadie tiene. Si el usuario no existe, se compara con este
# para que bcrypt tarde lo mismo: sin esto, «no existe» respondía en ~9 ms y
# «contraseña mala» en ~250 ms, y el tiempo delataba qué usuarios hay.
_HASH_FALSO = hash_password("usuario-que-no-existe-" + "x" * 16)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(LIMITE_REGISTRO)
def registrar(request: Request, datos: UserCreate, session: SessionDep):
    repetido = session.exec(
        select(User).where(
            or_(
                func.lower(User.username) == datos.username.lower(),
                func.lower(User.email) == datos.email,
            )
        )
    ).first()
    if repetido:
        logger.warning(
            "registro rechazado: usuario o email ya existen (%r)", datos.username
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El usuario o el email ya existen"
        )

    usuario = User(
        username=datos.username,
        email=datos.email,
        hashed_password=hash_password(datos.password),
    )
    session.add(usuario)
    try:
        session.commit()
    except IntegrityError:
        # Dos registros simultáneos con el mismo nombre: la base de datos decide.
        session.rollback()
        logger.warning(
            "registro rechazado: usuario o email ya existen (%r)", datos.username
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El usuario o el email ya existen"
        )
    session.refresh(usuario)
    logger.info("usuario registrado: %r (id=%s)", usuario.username, usuario.id)
    return usuario


def _emitir_par(session, usuario: User) -> TokenPair:
    """Access token (30 min) + refresh token (7 días), guardando el refresh en la BD."""
    refresh, jti, caduca = create_refresh_token(usuario.username, usuario.id)
    session.add(RefreshToken(jti=jti, user_id=usuario.id, expires_at=caduca))
    session.commit()
    return TokenPair(
        access_token=create_access_token(usuario.username, usuario.id),
        refresh_token=refresh,
    )


def _anular(session, *condiciones) -> int:
    """Marca como anulados los refresh tokens vivos que cumplan las condiciones.

    Es un UPDATE … WHERE revoked_at IS NULL: si dos peticiones usan a la vez el
    mismo token, solo una lo consigue (rowcount 1) y la otra cuenta como reutilización.
    """
    resultado = session.execute(
        update(RefreshToken)
        .where(RefreshToken.revoked_at.is_(None), *condiciones)
        .values(revoked_at=ahora())
    )
    session.commit()
    return resultado.rowcount


def _payload_refresh(token: str) -> dict | None:
    payload = decode_access_token(token)
    if payload is None or payload.get("type") != "refresh" or "jti" not in payload:
        return None
    return payload


@router.post("/login", response_model=TokenPair)
@limiter.limit(LIMITE_LOGIN)
def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    # Sin distinguir mayúsculas: «Ash», «ash» y «ASH» entran en la misma cuenta.
    usuario = session.exec(
        select(User).where(
            func.lower(User.username) == form.username.strip().lower()
        )
    ).first()
    # bcrypt se ejecuta SIEMPRE, exista o no el usuario: mismo mensaje y mismo tiempo.
    hash_guardado = usuario.hashed_password if usuario else _HASH_FALSO
    clave_correcta = verify_password(form.password, hash_guardado)
    # Una cuenta desactivada recibe el mismo error: ni tokens ni pistas.
    if usuario is None or not clave_correcta or not usuario.is_active:
        logger.warning("login fallido para %r", form.username)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            LOGIN_INCORRECTO,
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info("login correcto: %r (id=%s)", usuario.username, usuario.id)
    return _emitir_par(session, usuario)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(LIMITE_LOGIN)
def refrescar(request: Request, datos: RefreshRequest, session: SessionDep):
    """Cambia un refresh token por un par nuevo. El usado deja de valer (rotación)."""
    no_valido = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Refresh token no válido",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = _payload_refresh(datos.refresh_token)
    if payload is None:
        logger.warning("refresh rechazado: token no válido, caducado o de otro tipo")
        raise no_valido
    registro = session.get(RefreshToken, payload["jti"])
    if registro is None or registro.user_id != payload.get("user_id"):
        logger.warning("refresh rechazado: token desconocido")
        raise no_valido

    if _anular(session, RefreshToken.jti == registro.jti) == 0:
        # Ya estaba anulado y alguien lo vuelve a usar: o lo han robado, o lo ha usado
        # el ladrón antes que el usuario. No sabemos quién es quién, así que se anulan
        # todos los refresh tokens de esa cuenta y los dos tendrán que volver a entrar.
        anulados = _anular(session, RefreshToken.user_id == registro.user_id)
        logger.warning(
            "refresh token reutilizado (usuario id=%s): %s anulados",
            registro.user_id,
            anulados,
        )
        raise no_valido

    usuario = session.get(User, registro.user_id)
    if usuario is None or not usuario.is_active:
        logger.warning("refresh rechazado: usuario inexistente o inactivo")
        raise no_valido
    logger.info("refresh correcto: %r (id=%s)", usuario.username, usuario.id)
    return _emitir_par(session, usuario)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(LIMITE_LOGIN)
def logout(request: Request, datos: RefreshRequest, session: SessionDep):
    """Anula el refresh token. Responde 204 siempre, sea válido o no: así no sirve
    para averiguar qué tokens existen. El access token sigue valiendo hasta que
    caduca (máximo 30 min): el cliente debe borrarlo."""
    payload = _payload_refresh(datos.refresh_token)
    if payload is not None and _anular(session, RefreshToken.jti == payload["jti"]):
        logger.info(
            "logout: refresh token anulado (usuario id=%s)", payload.get("user_id")
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserRead)
@limiter.limit(LIMITE_AUTENTICADO)
def usuario_actual(request: Request, usuario: CurrentUser):
    """Devuelve el usuario dueño del token (sin la contraseña, por UserRead)."""
    return usuario
