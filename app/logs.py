"""Logging de la API: peticiones, autenticación, validación y límites (429).

Cada tipo de evento tiene su logger, para poder filtrarlos o subirles el nivel por
separado:

| Logger                       | Qué registra                                        |
|------------------------------|-----------------------------------------------------|
| `pokedex_api.peticiones`     | Una línea por petición: método, ruta, código, ms,   |
|                              | usuario, IP e id de petición                        |
| `pokedex_api.auth`           | Registros, logins (buenos y fallidos), tokens malos |
| `pokedex_api.validacion`     | Qué campos fallan en un 422                         |
| `pokedex_api.limites`        | Quién supera un límite y cuál (429)                 |
| `pokedex_api.pokeapi`        | Llamadas a la PokeAPI (en services/)                |

Nunca se registran contraseñas, tokens, cuerpos de petición ni query strings.
"""

import logging
import os
import re
import time
import uuid
from logging.handlers import RotatingFileHandler

from fastapi import Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth import decode_access_token
from app.limits import ip_cliente

FORMATO = "%(asctime)s %(levelname)s %(name)s · %(message)s"

logger_peticiones = logging.getLogger("pokedex_api.peticiones")
logger_validacion = logging.getLogger("pokedex_api.validacion")
logger_limites = logging.getLogger("pokedex_api.limites")

CABECERA_ID = "X-Request-ID"
# Si el cliente manda su propio id lo reutilizamos, pero solo si es "limpio":
# así nadie puede meter saltos de línea o basura en nuestros logs.
_ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def configurar_logging(nivel: str = "INFO", archivo: str | None = None) -> None:
    """Consola siempre; además, si se indica, un archivo que rota (1 MB, 3 copias)."""
    logging.basicConfig(level=nivel, format=FORMATO)
    logger_api = logging.getLogger("pokedex_api")
    logger_api.setLevel(nivel)
    if not archivo:
        return
    ruta = os.path.abspath(archivo)
    # Si ya escribe en ese archivo (p. ej. al recargar), no añadimos otro manejador.
    if any(
        isinstance(h, RotatingFileHandler) and h.baseFilename == ruta
        for h in logger_api.handlers
    ):
        return
    manejador = RotatingFileHandler(
        ruta, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    manejador.setFormatter(logging.Formatter(FORMATO))
    logger_api.addHandler(manejador)


def _id_peticion(request: Request) -> str:
    recibido = request.headers.get(CABECERA_ID, "")
    return recibido if _ID_VALIDO.fullmatch(recibido) else uuid.uuid4().hex[:12]


def _usuario(request: Request) -> str:
    """Quién hace la petición, sacado del token (sin ir a la base de datos)."""
    cabecera = request.headers.get("Authorization", "")
    if not cabecera.lower().startswith("bearer "):
        return "anónimo"
    payload = decode_access_token(cabecera[7:].strip())
    if not payload or "sub" not in payload:
        return "token-no-válido"
    return repr(str(payload["sub"]))  # repr: escapa saltos de línea


def _ip(request: Request) -> str:
    # La misma IP que usa el rate limiting (la real del cliente detrás de Render).
    return ip_cliente(request) or "-"


def _nivel(codigo: int) -> int:
    if codigo >= 500:
        return logging.ERROR
    if codigo >= 400:
        return logging.WARNING
    return logging.INFO


async def registrar_peticiones(request: Request, call_next):
    """Middleware: una línea de log por petición y cabecera X-Request-ID en la respuesta."""
    id_peticion = _id_peticion(request)
    request.state.id_peticion = id_peticion
    inicio = time.perf_counter()
    try:
        respuesta = await call_next(request)
    except Exception:
        ms = (time.perf_counter() - inicio) * 1000
        logger_peticiones.exception(
            "[%s] %s %s → error no controlado (%.1f ms) usuario=%s ip=%s",
            id_peticion,
            request.method,
            request.url.path,
            ms,
            _usuario(request),
            _ip(request),
        )
        raise

    ms = (time.perf_counter() - inicio) * 1000
    logger_peticiones.log(
        _nivel(respuesta.status_code),
        "[%s] %s %s → %s (%.1f ms) usuario=%s ip=%s",
        id_peticion,
        request.method,
        request.url.path,
        respuesta.status_code,
        ms,
        _usuario(request),
        _ip(request),
    )
    respuesta.headers[CABECERA_ID] = id_peticion
    return respuesta


async def registrar_error_validacion(request: Request, exc: RequestValidationError):
    """422: registra qué campos fallan y por qué, pero nunca los valores enviados."""
    errores = "; ".join(
        f"{'.'.join(str(p) for p in error.get('loc', ()))}: {error.get('msg', '?')}"
        for error in exc.errors()
    )
    logger_validacion.warning(
        "[%s] %s %s → 422 · %s",
        getattr(request.state, "id_peticion", "-"),
        request.method,
        request.url.path,
        errores,
    )
    return await request_validation_exception_handler(request, exc)


def registrar_limite_superado(request: Request, exc: RateLimitExceeded):
    """429: registra quién ha superado qué límite y deja a slowapi responder."""
    logger_limites.warning(
        "[%s] %s %s → 429 · límite %s superado · usuario=%s ip=%s",
        getattr(request.state, "id_peticion", "-"),
        request.method,
        request.url.path,
        exc.detail,
        _usuario(request),
        _ip(request),
    )
    return _rate_limit_exceeded_handler(request, exc)
