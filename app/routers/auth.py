"""Registro y login."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlmodel import or_, select

from app.auth import create_access_token, hash_password, verify_password
from app.dependencies import CurrentUser, SessionDep
from app.limits import LIMITE_AUTENTICADO, LIMITE_LOGIN, LIMITE_REGISTRO, limiter
from app.models import User, UserCreate, UserRead

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
            or_(User.username == datos.username, User.email == datos.email)
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


@router.post("/login")
@limiter.limit(LIMITE_LOGIN)
def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    usuario = session.exec(select(User).where(User.username == form.username)).first()
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
    return {
        "access_token": create_access_token(usuario.username, usuario.id),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserRead)
@limiter.limit(LIMITE_AUTENTICADO)
def usuario_actual(request: Request, usuario: CurrentUser):
    """Devuelve el usuario dueño del token (sin la contraseña, por UserRead)."""
    return usuario
