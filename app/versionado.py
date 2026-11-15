"""Deprecación de rutas de la v1 que ya tienen sucesora en la v2.

Política (explicada en «Versionado de la API» del README):
- Una ruta se marca obsoleta cuando su sucesora en la v2 ya está publicada.
- Sigue funcionando igual hasta la fecha de retirada (Sunset). Desde ese día responde 410 Gone.
- Mientras tanto, cada respuesta lo avisa con cabeceras estándar y cada uso queda en el log,
  para saber quién sigue usando la v1 antes de retirarla.
"""

import logging
from datetime import UTC, datetime
from email.utils import format_datetime

from fastapi import HTTPException, Request, Response, status

V1_OBSOLETA_DESDE = datetime(2026, 11, 14, tzinfo=UTC)  # publicación de la v2 (#14)
V1_RETIRADA = datetime(2027, 6, 30, tzinfo=UTC)  # al menos 6 meses de convivencia

logger = logging.getLogger("pokedex_api.versionado")


def _ahora() -> datetime:
    # Aparte para que los tests puedan simular que ya pasó la fecha de retirada.
    return datetime.now(UTC)


def obsoleta_en_v1(request: Request, response: Response) -> None:
    """Dependencia para las rutas de la v1 que ya tienen sucesora en la v2.

    - Deprecation (RFC 9745): desde cuándo está obsoleta, como «@<segundos Unix>».
    - Sunset (RFC 8594): cuándo se retira, en formato de fecha HTTP.
    - Link rel="successor-version": la misma ruta en la v2.

    Pasada la fecha de retirada, responde 410 Gone sin ejecutar el endpoint.
    """
    sucesora = request.url.path.replace("/api/v1/", "/api/v2/", 1)
    enlace = f'<{sucesora}>; rel="successor-version"'
    if _ahora() >= V1_RETIRADA:
        logger.warning("ruta retirada: %s %s", request.method, request.url.path)
        raise HTTPException(
            status.HTTP_410_GONE,
            f"Esta ruta se retiró el {V1_RETIRADA:%Y-%m-%d}. Usa {sucesora}",
            headers={"Link": enlace},
        )
    response.headers["Deprecation"] = f"@{int(V1_OBSOLETA_DESDE.timestamp())}"
    response.headers["Sunset"] = format_datetime(V1_RETIRADA, usegmt=True)
    response.headers["Link"] = enlace
    logger.info(
        "uso de ruta obsoleta: %s %s (sucesora: %s)",
        request.method,
        request.url.path,
        sucesora,
    )
