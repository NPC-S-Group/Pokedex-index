"""Registro y login."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlmodel import or_, select

from app.auth import create_access_token, hash_password, verify_password
from app.dependencies import SessionDep
from app.limits import LIMITE_LOGIN, LIMITE_REGISTRO, limiter
from app.models import User, UserCreate, UserRead

# Los nombres van con %r: escapa saltos de línea y nadie puede falsear líneas del log.
logger = logging.getLogger("pokedex_api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


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
    # Mismo mensaje para «no existe» y «contraseña mala»: no regalamos qué usuarios hay.
    if usuario is None or not verify_password(form.password, usuario.hashed_password):
        logger.warning("login fallido para %r", form.username)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info("login correcto: %r (id=%s)", usuario.username, usuario.id)
    return {
        "access_token": create_access_token(usuario.username, usuario.id),
        "token_type": "bearer",
    }
