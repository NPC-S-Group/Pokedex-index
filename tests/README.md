# `tests/` · pruebas

Se ejecutan con:
```bash
pytest --cov=app --cov-report=term-missing
```
El CI exige **cobertura ≥ 80 %**. El enunciado pide **mínimo 15 tests**.

| Archivo | Qué prueba | Tests | Tarea |
|---|---|---|---|
| `conftest.py` | Fixtures comunes (no son tests) | — | Jorge |
| `test_health.py` | `/health` y `/docs` | 2 | #3 |
| `test_teams.py` | Equipos: límites, propiedad, PUT y borrado | 15 | #6 |
| `test_teams_export.py` | Equipo en PDF: páginas, cabeceras, propiedad, imágenes y estadísticas combinadas | 8 | #13 |
| `test_rate_limit_cors.py` | 429 de cada nivel y CORS | 8 | #9 |
| `test_auth.py` | Registro, login, token y usuario actual | 30 | #4 Miguel |
| `test_refresh.py` | Refresh tokens: par en el login, rotación, reutilización, tipos separados, caducidad, logout y 429 | 27 | mejora de #4 Miguel |
| `test_pokedex.py` | CRUD, filtros, orden, paginación y propiedad | 41 | #7 Miguel |
| `test_stats.py` | `/stats`: tipo más común (empates, doble tipo), racha (huecos, hoy o ayer, zona horaria), tipos guardados y la columna nueva en una BD antigua | 26 | #12 Henar |
| `test_export.py` | Exportar a CSV y PDF: filtros, orden, sin paginar, inyección CSV, caracteres raros y 429 | 22 | #11 Miguel |
| `test_api_v2.py` | API v2: forma de la respuesta, sobre de paginación, filtros, propiedad, que la v1 no cambia y 429 | 19 | #14 Miguel |
| `test_pokeapi_service.py` | Servicio con mock: OK, errores, timeouts y logging | 31 | #5 Henar |
| `test_pokemon.py` | Búsqueda (nombre, tipo, paginación, caché), detalle y ficha PDF, con la PokeAPI simulada | 37 | #8 Henar |
| `test_logging.py` | Logging de peticiones, auth, 422 y 429; que no se filtren contraseñas ni tokens | 22 | #10 Henar |

**Avance:** el número de tests y la cobertura de cada cambio se ven en el CI (pestaña *Actions* de cada PR) y en las notas de cada release. Así no hay que editar esta línea en cada PR, que provocaba conflictos.

## Fixtures de `conftest.py`
| Fixture | Para qué |
|---|---|
| `client` | `TestClient` con una BD SQLite **en memoria** (nueva en cada test) y una **PokeAPI falsa** |
| `test_user` / `auth_headers` | El usuario `ash` y su cabecera `Authorization: Bearer …` |
| `other_user` / `other_headers` | El usuario `gary`, para probar que no se tocan datos ajenos |
| `add_to_pokedex(usuario, 25, 1, …)` | Mete Pokémon en la Pokédex sin pasar por la API |

- La PokeAPI falsa conoce 1, 4, 7, 25, 133, 143 y 150. Cualquier otro id da 404.
- El limitador se reinicia en cada test, así que no hay 429 inesperados.
- Para tests asíncronos: `@pytest.mark.anyio` (no hace falta `pytest-asyncio`).

```python
def test_ejemplo(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    r = client.get("/api/v1/pokedex", headers=auth_headers)
    assert r.json()[0]["pokemon_name"] == "pikachu"
```
