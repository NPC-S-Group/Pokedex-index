# `app/services/` · servicios externos

| Archivo | Qué hace | Estado | Tarea |
|---|---|---|---|
| `pokeapi_service.py` | Cliente asíncrono (`httpx`) de la PokeAPI. Traduce errores (404 → 404, timeout → 504, caída → 502), registra cada llamada y simplifica la respuesta. También busca (por nombre y tipo, con caché de 24 h) y descarga las imágenes de la ficha | ✅ con tests (100 %) | #5, #8 Henar |
| `ficha_pdf.py` | Genera la ficha A5 en PDF con `fpdf2`: cabecera del color del tipo, imagen, datos, habilidades y barras de estadísticas. `dibujar_ficha()` añade la ficha a un PDF ya abierto (la usa el export de equipos) | ✅ con tests (100 %) | #8 Henar |
| `equipo_pdf.py` | PDF del equipo: portada con estadísticas combinadas (`estadisticas_combinadas()`: suma, media, total y tipos) y una ficha por miembro | ✅ con tests (100 %) | #13 Jorge |
| `export_service.py` | Pokédex a CSV (UTF-8 con BOM, celdas protegidas contra inyección de fórmulas) y a PDF en tabla con `fpdf2` (cabecera con filtros y totales, salta de página). Reutiliza `_texto` de `ficha_pdf.py` | ✅ | #11 Miguel |

**PDF:** todo el proyecto usa `fpdf2`. Si un export nuevo (por ejemplo la Pokédex, #11) necesita PDF, que reutilice estos módulos en lugar de añadir otra librería.

## Cómo se usa
Los endpoints no crean el cliente: lo reciben con la dependencia `ServicioPokeAPI` (en `app/dependencies.py`). Por eso, en los tests se sustituye por `PokeAPIFalsa` (ver `tests/conftest.py`) y nunca se sale a internet.
