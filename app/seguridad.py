"""Cabeceras de seguridad que se añaden a todas las respuestas.

Son instrucciones para el navegador. Una API que solo devuelve JSON no las
necesita tanto como una web, pero cuestan una línea cada una y cierran
ataques típicos si algún día un navegador abre una respuesta nuestra.
"""

from fastapi import Request

CABECERAS = {
    # No adivinar el tipo de contenido: un JSON nunca se ejecuta como HTML o JS.
    "X-Content-Type-Options": "nosniff",
    # Nadie puede meter la API dentro de un <iframe> (clickjacking).
    "X-Frame-Options": "DENY",
    # No contar a otras webs desde qué URL se llegó (podría llevar datos).
    "Referrer-Policy": "no-referrer",
}
# «Ven siempre por HTTPS durante un año». Solo se manda si la petición llegó por
# HTTPS (en Render, el proxy lo indica en X-Forwarded-Proto); por HTTP no vale.
HSTS = "max-age=31536000; includeSubDomains"
# Las respuestas JSON no cargan nada: se prohíbe todo. /docs y /redoc no la llevan
# porque Swagger y ReDoc cargan sus scripts y estilos de un CDN.
CSP_API = "default-src 'none'; frame-ancestors 'none'"
_SIN_CSP = ("/docs", "/redoc")


def _por_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[-1].strip()
    return request.url.scheme == "https" or proto == "https"


async def cabeceras_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    for nombre, valor in CABECERAS.items():
        respuesta.headers.setdefault(nombre, valor)
    if _por_https(request):
        respuesta.headers.setdefault("Strict-Transport-Security", HSTS)
    ruta = request.url.path
    if not ruta.startswith(_SIN_CSP):
        respuesta.headers.setdefault("Content-Security-Policy", CSP_API)
    if ruta.startswith("/api/v1/auth"):
        # Los tokens no se guardan en la caché del navegador ni de ningún proxy.
        respuesta.headers["Cache-Control"] = "no-store"
    return respuesta
