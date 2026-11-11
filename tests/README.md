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
| `test_rate_limit_cors.py` | 429 de cada nivel y CORS | 8 | #9 |
| `test_auth.py` | Registro, login y token | ❌ falta | #4 Miguel |
| `test_pokedex.py` | CRUD, filtros, orden, paginación y propiedad | 41 | #7 Miguel |
| `test_pokeapi_service.py` | Servicio con mock: OK, errores, timeouts y logging | 31 | #5 Henar |
| `test_logging.py` | Logging de peticiones, auth, 422 y 429; que no se filtren contraseñas ni tokens | 22 | #10 Henar |

**Avance (10 nov):** 25 tests y 81 % de cobertura.  
**Avance (11 nov):** 78 tests y 90 % de cobertura.  
**Avance (11 nov, tarde):** tests de auth (#4, PR #28) y del CRUD de la Pokédex (#7, PR #29): 149 tests y 99 % de cobertura al integrar los dos.

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
