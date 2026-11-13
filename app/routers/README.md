# `app/routers/` · endpoints

Un archivo por grupo de endpoints. Todos se registran en `main.py` con el prefijo `/api/v1`.

| Archivo | Endpoints | Límite | Estado | Tarea |
|---|---|---|---|---|
| `auth.py` | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | 5/h, 10/min y 100/min | ✅ código · ✅ tests | #4 Miguel |
| `pokemon.py` | `GET /pokemon/search?q=&type=&limit=&offset=`, `GET /pokemon/{id_or_name}`, `GET /pokemon/{id_or_name}/card` (PDF) | 30/min | ✅ con tests (100 %) | #8 Henar |
| `pokedex.py` | `POST`, `GET` (filtros, orden y paginación), `GET /{id}`, `PATCH`, `DELETE` | 30/min (POST), 100/min | ✅ código · ✅ tests | #7 Miguel |
| | `GET /pokedex/stats`: total, capturados, favoritos, %, `most_common_type` y `capture_streak_days` | 100/min | ✅ con tests (100 %) | #12 Henar |
| | `GET /pokedex/export?format=csv\|pdf` con los filtros y el orden del listado | 10/min | ✅ código · ✅ tests | #11 Miguel |
| `teams.py` | `POST`, `GET`, `GET /{id}`, `PUT`, `DELETE` | 100/min | ✅ con tests (100 %) | #6 Jorge |
| | `GET /teams/{id}/export` (PDF) | 30/min | ✅ con tests (100 %) | #13 Jorge |

## Reglas comunes
- **Propiedad:** cada usuario solo ve y toca lo suyo. Si algo es de otro, responde **404** (no 403), para no confirmar que existe.
- **Rate limiting:** cada endpoint lleva `@limiter.limit(...)` y `request: Request` como primer parámetro, porque slowapi lo necesita. No hay límite por defecto: si añades un endpoint, ponle su decorador (ver `app/limits.py`).
- **Códigos:** 422 = petición mal formada (lo detecta Pydantic); 400 = regla de negocio no cumplida; 409 = duplicado; 401 = sin token o token inválido; 429 = límite superado.

## Equipos (`teams.py`)
- De 1 a 6 Pokémon, sin repetidos (422), y todos de **tu** Pokédex (400 con la lista de los que faltan).
- La posición (1–6) sigue el orden de `pokemon_ids`.
- `PUT` reemplaza el equipo entero. Los miembros antiguos se borran solos (cascada `delete-orphan`).
- Si borras un Pokémon de la Pokédex, sale de sus equipos.
- `GET /{id}/export` descarga un PDF A5: portada (miembros, suma y media de cada estadística, total del equipo y tipos) y la ficha de cada Pokémon, la misma que `/pokemon/{id}/card`. Pide a la PokeAPI los datos y las imágenes de los miembros a la vez (`asyncio.gather`), y por eso tiene el límite de 30/min.
