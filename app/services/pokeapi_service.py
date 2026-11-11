"""Cliente de la PokeAPI: llama fuera, traduce los errores y simplifica la respuesta.

Cómo se traduce cada fallo de la PokeAPI a una respuesta nuestra:

| Qué pasa en la PokeAPI                      | Qué devolvemos            |
|---------------------------------------------|---------------------------|
| No existe el Pokémon (404)                  | 404 Not Found             |
| Identificador vacío o con caracteres raros  | 422 (sin llamar fuera)    |
| Tarda más que el timeout                    | 504 Gateway Timeout       |
| No se puede conectar / error de red         | 502 Bad Gateway           |
| Responde 5xx, 429 u otro error              | 502 Bad Gateway           |
| Responde algo que no es JSON o le faltan    | 502 Bad Gateway           |
| campos que necesitamos                      |                           |

Todo queda registrado en el logger "pokedex_api.pokeapi".
"""

import logging
import re
import time

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger("pokedex_api.pokeapi")

# Nombres de la PokeAPI: minúsculas, dígitos y guiones (p. ej. "mr-mime", "porygon2").
_IDENTIFICADOR_VALIDO = re.compile(r"^[a-z0-9-]+$")
_STATS = ("hp", "attack", "defense", "speed")


class PokeAPIService:
    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Los tests inyectan un httpx.MockTransport para no salir a internet.
        self._transport = transport

    async def get_pokemon(self, identificador: int | str) -> dict:
        clave = self._normalizar(identificador)
        datos = await self._get_json(f"/pokemon/{clave}", identificador)
        return self._simplificar(datos)

    @staticmethod
    def _normalizar(identificador: int | str) -> str:
        clave = str(identificador).strip().lower()
        if not _IDENTIFICADOR_VALIDO.fullmatch(clave):
            logger.warning("identificador no válido: %r", identificador)
            raise HTTPException(
                422,  # Unprocessable Content
                f"Identificador de Pokémon no válido: {identificador!r}",
            )
        return clave

    async def _get_json(self, ruta: str, identificador: int | str) -> dict:
        url = f"{self.base_url}{ruta}"
        inicio = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport
            ) as cliente:
                respuesta = await cliente.get(url)
        except httpx.TimeoutException:
            logger.error("timeout (%.1f s) en GET %s", self.timeout, url)
            raise HTTPException(
                status.HTTP_504_GATEWAY_TIMEOUT, "PokeAPI no responde"
            ) from None
        except httpx.HTTPError as error:
            logger.error("error de red en GET %s: %s", url, type(error).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "PokeAPI no disponible"
            ) from None

        ms = (time.perf_counter() - inicio) * 1000
        logger.info("GET %s → %s (%.1f ms)", url, respuesta.status_code, ms)

        if respuesta.status_code == 404:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"No existe el Pokémon {identificador}"
            )
        if respuesta.is_error:
            logger.error("PokeAPI respondió %s en GET %s", respuesta.status_code, url)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "PokeAPI no disponible")

        try:
            datos = respuesta.json()
        except ValueError:
            logger.error("respuesta no JSON en GET %s", url)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Respuesta no válida de PokeAPI"
            ) from None
        if not isinstance(datos, dict):
            logger.error("respuesta JSON inesperada en GET %s", url)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Respuesta no válida de PokeAPI"
            )
        return datos

    @staticmethod
    def _simplificar(bruto: dict) -> dict:
        # La frontera del sistema: lo ajeno entra aquí y sale con nuestro vocabulario.
        try:
            stats = {s["stat"]["name"]: s["base_stat"] for s in bruto.get("stats", [])}
            return {
                "id": bruto["id"],
                "name": bruto["name"],
                # Algunos Pokémon (formas raras) no tienen sprite: None, no error.
                "sprite": (bruto.get("sprites") or {}).get("front_default"),
                "types": [t["type"]["name"] for t in bruto.get("types", [])],
                "stats": {clave: stats.get(clave) for clave in _STATS},
            }
        except (KeyError, TypeError, AttributeError):
            logger.error("respuesta de PokeAPI con formato inesperado")
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Respuesta no válida de PokeAPI"
            ) from None
