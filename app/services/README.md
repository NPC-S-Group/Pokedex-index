# `app/services/` · servicios externos

| Archivo | Qué hace | Estado | Tarea |
|---|---|---|---|
| `pokeapi_service.py` | Cliente asíncrono (`httpx`) de la PokeAPI. Traduce errores (404 → 404, timeout → 504, caída → 502) y simplifica la respuesta a `{id, name, sprite, types, stats}` | ✅ código · ❌ logging de llamadas · ❌ tests con mock | #5 Henar |

## Cómo se usa
Los endpoints no crean el cliente: lo reciben con la dependencia `ServicioPokeAPI` (en `app/dependencies.py`). Por eso, en los tests se sustituye por `PokeAPIFalsa` (ver `tests/conftest.py`) y nunca se sale a internet.

## Pendiente
- Logging de cada llamada: URL, status y duración (lo pide el enunciado, #5/#10).
- Búsqueda por nombre y datos para la ficha `/card` (#8).
- Tests del servicio con `httpx` simulado (`@pytest.mark.anyio`).
