"""Limitador de peticiones, en su propio módulo para que los routers lo importen sin ciclos.

Cuatro niveles (justificados en «Decisiones de diseño» del README):
- Públicos (registro, login): los más estrictos, frenan fuerza bruta y spam de cuentas.
- Llaman a la PokeAPI: estrictos, para no agotar un servicio externo que no es nuestro.
- Exportar a CSV o PDF: intermedio; recorre toda la Pokédex y genera un fichero.
- Resto de endpoints autenticados: generosos; es el uso normal de la API.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

LIMITE_REGISTRO = "5/hour"
LIMITE_LOGIN = "10/minute"
LIMITE_POKEAPI = "30/minute"
LIMITE_EXPORTAR = "10/minute"
LIMITE_AUTENTICADO = "100/minute"

# Cada endpoint lleva su @limiter.limit explícito. No usamos default_limits porque
# slowapi 0.1.10 no encuentra las rutas de los routers en FastAPI >= 0.16x y el
# límite por defecto no se aplicaría a ninguna (comprobado en los tests).
limiter = Limiter(key_func=get_remote_address)
