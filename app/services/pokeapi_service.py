"""Cliente de la PokeAPI: llama fuera, traduce los errores y simplifica la respuesta.

Cómo se traduce cada fallo de la PokeAPI a una respuesta nuestra:

| Qué pasa en la PokeAPI                      | Qué devolvemos            |
|---------------------------------------------|---------------------------|
| No existe el Pokémon o el tipo (404)        | 404 Not Found             |
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
from typing import ClassVar
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger("pokedex_api.pokeapi")

# Nombres de la PokeAPI: minúsculas, dígitos y guiones (p. ej. "mr-mime", "porygon2").
_IDENTIFICADOR_VALIDO = re.compile(r"^[a-z0-9-]+$")
_STATS = ("hp", "attack", "defense", "special-attack", "special-defense", "speed")

# La lista de nombres apenas cambia (sale un juego nuevo cada pocos años), así que
# se guarda en memoria un día: buscar no cuesta una llamada a la PokeAPI cada vez.
CACHE_SEGUNDOS = 24 * 60 * 60
# Más que todos los Pokémon que existen (~1300 con formas): una sola página.
_LIMITE_LISTADO = 100_000

# Las imágenes solo se descargan del repositorio oficial de sprites de la PokeAPI.
_HOSTS_IMAGENES = {"raw.githubusercontent.com"}
_MAX_BYTES_IMAGEN = 2 * 1024 * 1024
SPRITE_POR_ID = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png"
)


def _error_formato() -> HTTPException:
    logger.error("respuesta de PokeAPI con formato inesperado")
    return HTTPException(status.HTTP_502_BAD_GATEWAY, "Respuesta no válida de PokeAPI")


def _id_desde_url(url: str) -> int:
    """'https://pokeapi.co/api/v2/pokemon/25/' → 25."""
    return int(url.rstrip("/").rsplit("/", 1)[1])


class PokeAPIService:
    # Compartida entre instancias: el servicio se crea en cada petición.
    _cache: ClassVar[dict[str, tuple[float, object]]] = {}

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

    @classmethod
    def limpiar_cache(cls) -> None:
        cls._cache.clear()

    # ─────────────────────────── Detalle ───────────────────────────

    async def get_pokemon(self, identificador: int | str) -> dict:
        clave = self._normalizar(identificador)
        datos = await self._get_json(
            f"/pokemon/{clave}", f"No existe el Pokémon {identificador}"
        )
        return self._simplificar(datos)

    # ─────────────────────────── Búsqueda ───────────────────────────

    async def buscar(
        self,
        texto: str | None = None,
        tipo: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Busca por parte del nombre y/o por tipo. Devuelve una página ordenada por id."""
        candidatos = (
            await self._pokemon_de_tipo(tipo)
            if tipo
            else await self._todos_los_nombres()
        )
        if texto:
            # "Mr Mime" → "mr-mime": la PokeAPI usa guiones en vez de espacios.
            aguja = texto.strip().lower().replace(" ", "-")
            candidatos = [p for p in candidatos if aguja in p["name"]]
        candidatos = sorted(candidatos, key=lambda p: p["id"])
        pagina = candidatos[offset : offset + limit]
        return {
            "count": len(candidatos),
            "limit": limit,
            "offset": offset,
            "results": [
                {**p, "sprite": SPRITE_POR_ID.format(id=p["id"])} for p in pagina
            ],
        }

    async def _todos_los_nombres(self) -> list[dict]:
        def extraer(datos: dict) -> list[dict]:
            return [
                {"id": _id_desde_url(p["url"]), "name": p["name"]}
                for p in datos["results"]
            ]

        return await self._con_cache(
            "nombres",
            f"/pokemon?limit={_LIMITE_LISTADO}&offset=0",
            "No se encuentra el listado de Pokémon",
            extraer,
        )

    async def _pokemon_de_tipo(self, tipo: str) -> list[dict]:
        clave = self._normalizar(tipo, "tipo")

        def extraer(datos: dict) -> list[dict]:
            return [
                {"id": _id_desde_url(p["pokemon"]["url"]), "name": p["pokemon"]["name"]}
                for p in datos["pokemon"]
            ]

        return await self._con_cache(
            f"tipo:{clave}", f"/type/{clave}", f"No existe el tipo {tipo}", extraer
        )

    async def _con_cache(self, clave, ruta, no_encontrado, extraer) -> list[dict]:
        clave = f"{self.base_url}|{clave}"
        guardado = self._cache.get(clave)
        if guardado and time.monotonic() - guardado[0] < CACHE_SEGUNDOS:
            return guardado[1]
        datos = await self._get_json(ruta, no_encontrado)
        try:
            resultado = extraer(datos)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            raise _error_formato() from None
        self._cache[clave] = (time.monotonic(), resultado)
        return resultado

    # ─────────────────────────── Imágenes ───────────────────────────

    async def descargar_imagen(self, url: str | None) -> bytes | None:
        """Descarga una imagen para la ficha. Si algo falla devuelve None: sin imagen."""
        if not url:
            return None
        partes = urlparse(url)
        if partes.scheme != "https" or partes.hostname not in _HOSTS_IMAGENES:
            logger.warning("imagen descartada, host no permitido: %r", url)
            return None
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport
            ) as cliente:
                respuesta = await cliente.get(url)
        except httpx.HTTPError as error:
            logger.warning("no se pudo descargar %s: %s", url, type(error).__name__)
            return None
        if respuesta.is_error or len(respuesta.content) > _MAX_BYTES_IMAGEN:
            logger.warning(
                "imagen no válida en %s (código %s, %s bytes)",
                url,
                respuesta.status_code,
                len(respuesta.content),
            )
            return None
        return respuesta.content

    # ─────────────────────────── Internos ───────────────────────────

    @staticmethod
    def _normalizar(identificador: int | str, que: str = "Pokémon") -> str:
        clave = str(identificador).strip().lower()
        if not _IDENTIFICADOR_VALIDO.fullmatch(clave):
            logger.warning("identificador no válido: %r", identificador)
            raise HTTPException(
                422,  # Unprocessable Content
                f"Identificador de {que} no válido: {identificador!r}",
            )
        return clave

    async def _get_json(self, ruta: str, no_encontrado: str) -> dict:
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
            raise HTTPException(status.HTTP_404_NOT_FOUND, no_encontrado)
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
            sprites = bruto.get("sprites") or {}
            oficial = ((sprites.get("other") or {}).get("official-artwork") or {}).get(
                "front_default"
            )
            altura, peso = bruto.get("height"), bruto.get("weight")
            return {
                "id": bruto["id"],
                "name": bruto["name"],
                # Algunos Pokémon (formas raras) no tienen sprite: None, no error.
                "sprite": sprites.get("front_default"),
                "sprites": {
                    "front_default": sprites.get("front_default"),
                    "back_default": sprites.get("back_default"),
                    "front_shiny": sprites.get("front_shiny"),
                    "official_artwork": oficial,
                },
                "types": [t["type"]["name"] for t in bruto.get("types", [])],
                # La PokeAPI da decímetros y hectogramos: lo pasamos a m y kg.
                "height_m": altura / 10 if altura is not None else None,
                "weight_kg": peso / 10 if peso is not None else None,
                "abilities": [
                    {
                        "name": a["ability"]["name"],
                        "is_hidden": bool(a.get("is_hidden")),
                    }
                    for a in bruto.get("abilities", [])
                ],
                # "special-attack" → "special_attack": más cómodo en JSON y en Python.
                "stats": {c.replace("-", "_"): stats.get(c) for c in _STATS},
            }
        except (KeyError, TypeError, AttributeError):
            raise _error_formato() from None
