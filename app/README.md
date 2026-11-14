# `app/` · código de la API

Paquete principal de la Pokédex API (FastAPI + SQLModel).

| Archivo | Qué hace | Estado |
|---|---|---|
| `main.py` | Crea la app: CORS, rate limiting, logging, routers bajo `/api/v1` (y la v2 de ejemplo bajo `/api/v2`) y `/health` | ✅ |
| `logs.py` | Middleware de logging de peticiones y registro de 422 y 429 (ver «Logging» en el README) | ✅ (#10) |
| `config.py` | Lee `.env` en un objeto `Settings` validado. Sin `SECRET_KEY` la app no arranca | ✅ |
| `database.py` | Motor de la BD y una sesión por petición (`get_session`) | ✅ |
| `models.py` | Tablas (`User`, `RefreshToken`, `PokedexEntry`, `Team`, `TeamMember`) y esquemas de entrada y salida (`*Create`, `*Read`, `*Update`, y `*V2` de la API v2) | ✅ |
| `auth.py` | Hash de contraseñas con bcrypt y creación y lectura de JWT: access token (24 h) y refresh token (7 días) | ✅ (#4) |
| `dependencies.py` | Dependencias comunes: `SessionDep`, `CurrentUser` (usuario del token) y `ServicioPokeAPI` | ✅ |
| `limits.py` | Limitador de slowapi y los cuatro niveles de límite | ✅ (#9) |
| `routers/` | Endpoints, un archivo por grupo ([ver README](routers/README.md)) | 🟡 |
| `services/` | Clientes de servicios externos ([ver README](services/README.md)) | 🟡 |

## Cómo encaja
```
petición → logging → rate limiting → CORS → endpoint (router)
                                 ├─ CurrentUser  → auth.py (JWT) → BD
                                 ├─ SessionDep   → database.py
                                 └─ ServicioPokeAPI → services/pokeapi_service.py → PokeAPI
```

## Avance
El estado de cada tarea está en el [tablero del proyecto](https://github.com/orgs/NPC-S-Group/projects/1) y en los [hitos](https://github.com/NPC-S-Group/Pokedex-index/milestones). Lo que trae cada versión, en las [releases](https://github.com/NPC-S-Group/Pokedex-index/releases).

Leyenda: ✅ hecho · 🟡 a medias · ❌ falta
