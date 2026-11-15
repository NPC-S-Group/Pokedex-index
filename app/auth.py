"""Contraseñas (bcrypt) y testigos (JWT).

Dos tipos de JWT, distinguidos por el claim «type»:
- access (30 min): va en cada petición, en la cabecera Authorization.
- refresh (7 días): solo sirve para pedir un par nuevo en /auth/refresh.
"""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# bcrypt directamente: passlib lleva años sin mantenerse y falla con bcrypt ≥ 4.1
# (AttributeError: module 'bcrypt' has no attribute '__about__').


# bcrypt solo usa los primeros 72 bytes y bcrypt ≥ 5 lanza un error con más: sin
# controlarlo, una contraseña larga daba un 500 en el registro y en el login.
MAX_BYTES_PASSWORD = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    datos = password.encode()
    if len(datos) > MAX_BYTES_PASSWORD:
        # Ninguna contraseña guardada puede ser tan larga (el registro lo impide):
        # es incorrecta. Se ejecuta bcrypt igualmente para tardar lo mismo.
        bcrypt.checkpw(datos[:MAX_BYTES_PASSWORD], hashed.encode())
        return False
    return bcrypt.checkpw(datos, hashed.encode())


def create_access_token(username: str, user_id: int) -> str:
    ahora = datetime.now(UTC)
    minutos = settings.access_token_expire_minutes
    payload = {
        "sub": username,
        "user_id": user_id,
        "type": "access",
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(username: str, user_id: int) -> tuple[str, str, datetime]:
    """Devuelve (token, jti, caducidad). El jti identifica el token en la tabla
    RefreshToken, para poder anularlo (rotación, logout o reutilización)."""
    ahora = datetime.now(UTC)
    caduca = ahora + timedelta(days=settings.refresh_token_expire_days)
    jti = uuid.uuid4().hex
    payload = {
        "sub": username,
        "user_id": user_id,
        "type": "refresh",
        "jti": jti,
        "iat": ahora,
        "exp": caduca,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, jti, caduca


def decode_access_token(token: str) -> dict | None:
    """Comprueba firma y caducidad de cualquiera de nuestros JWT; el tipo lo mira quien llama."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        # Firma mala, caducado o inventado → None, no excepción.
        # Quien llama decide qué código HTTP le corresponde a eso.
        return None
