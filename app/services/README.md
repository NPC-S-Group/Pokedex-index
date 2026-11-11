# `app/services/` · servicios externos

| Archivo | Qué hace | Estado | Tarea |
|---|---|---|---|
| `pokeapi_service.py` | Cliente asíncrono (`httpx`) de la PokeAPI. Traduce errores (404 → 404, timeout → 504, caída → 502), registra cada llamada y simplifica la respuesta. También busca (por nombre y tipo, con caché de 24 h) y descarga las imágenes de la ficha | ✅ con tests (100 %) | #5, #8 Henar |
| `ficha_pdf.py` | Genera la ficha A5 en PDF con `fpdf2`: cabecera del color del tipo, imagen, datos, habilidades y barras de estadísticas | ✅ con tests (100 %) | #8 Henar |

## Cómo se usa
Los endpoints no crean el cliente: lo reciben con la dependencia `ServicioPokeAPI` (en `app/dependencies.py`). Por eso, en los tests se sustituye por `PokeAPIFalsa` (ver `tests/conftest.py`) y nunca se sale a internet.
