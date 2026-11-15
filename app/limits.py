"""Limitador de peticiones, en su propio módulo para que los routers lo importen sin ciclos.

Cuatro niveles (justificados en «Decisiones de diseño» del README):
- Públicos (registro, login): los más estrictos, frenan fuerza bruta y spam de cuentas.
- Llaman a la PokeAPI: estrictos, para no agotar un servicio externo que no es nuestro.
- Exportar a CSV o PDF: intermedio; recorre toda la Pokédex y genera un fichero.
- Resto de endpoints autenticados: generosos; es el uso normal de la API.

Además, el login tiene un segundo límite POR CUENTA (no por IP): aunque alguien
cambie de IP, no puede probar más de 5 contraseñas cada 15 minutos contra un usuario.
"""

from fastapi import Request
from limits import parse
from slowapi import Limiter

from app.config import settings

LIMITE_REGISTRO = "5/hour"
LIMITE_LOGIN = "10/minute"
LIMITE_LOGIN_CUENTA = "5/15minutes"
LIMITE_POKEAPI = "30/minute"
LIMITE_EXPORTAR = "10/minute"
LIMITE_AUTENTICADO = "100/minute"


def ip_cliente(request: Request) -> str:
    """IP real del cliente, también detrás del proxy de Render.

    Detrás de un proxy, la conexión llega siempre desde la IP del proxy: si
    limitamos por ella, todos los usuarios comparten el mismo contador. La IP
    real viene en la cabecera X-Forwarded-For («cliente, proxy1, proxy2…»), pero
    la parte de la izquierda la escribe el cliente y puede inventársela. Por eso
    se cuenta desde la DERECHA: la última entrada la añadió nuestro proxy.
    """
    saltos = settings.saltos_proxy
    if saltos:
        cabecera = request.headers.get("x-forwarded-for", "")
        ips = [ip.strip() for ip in cabecera.split(",") if ip.strip()]
        if len(ips) >= saltos:
            return ips[-saltos]
    return request.client.host if request.client else "desconocida"


# Cada endpoint lleva su @limiter.limit explícito. No usamos default_limits porque
# slowapi 0.1.10 no encuentra las rutas de los routers en FastAPI >= 0.16x y el
# límite por defecto no se aplicaría a ninguna (comprobado en los tests).
limiter = Limiter(key_func=ip_cliente)

# --- Límite de logins fallidos por cuenta -------------------------------------
# Usa el mismo almacén que slowapi (memoria), así limiter.reset() lo limpia también.
_por_cuenta = parse(LIMITE_LOGIN_CUENTA)


def _clave(username: str) -> tuple[str, str]:
    return ("login-cuenta", username.strip().lower())


def cuenta_bloqueada(username: str) -> bool:
    """True si ya se han gastado los intentos fallidos de esa cuenta."""
    return not limiter.limiter.test(_por_cuenta, *_clave(username))


def apuntar_fallo(username: str) -> None:
    limiter.limiter.hit(_por_cuenta, *_clave(username))


def olvidar_fallos(username: str) -> None:
    """Tras un login correcto, el contador de esa cuenta vuelve a cero."""
    limiter.limiter.clear(_por_cuenta, *_clave(username))
