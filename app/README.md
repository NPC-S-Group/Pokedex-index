# `app/` · código de la API

Paquete principal de la Pokédex API (FastAPI + SQLModel).

| Archivo | Qué hace | Estado |
|---|---|---|
| `main.py` | Crea la app: CORS, rate limiting, logging, routers bajo `/api/v1` y `/health` | ✅ |
| `logs.py` | Middleware de logging de peticiones y registro de 422 y 429 (ver «Logging» en el README) | ✅ (#10) |
| `config.py` | Lee `.env` en un objeto `Settings` validado. Sin `SECRET_KEY` la app no arranca | ✅ |
| `database.py` | Motor de la BD y una sesión por petición (`get_session`) | ✅ |
| `models.py` | Tablas (`User`, `PokedexEntry`, `Team`, `TeamMember`) y esquemas de entrada y salida (`*Create`, `*Read`, `*Update`) | ✅ |
| `auth.py` | Hash de contraseñas con bcrypt y creación y lectura de JWT | ✅ código · ❌ tests (#4) |
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
- **10 nov:** base del hito 4 (#2), resto de archivos iniciales, equipos (#6) y rate limiting con CORS (#9).
- **11 nov:** cliente de PokeAPI (#5) y logging completo (#10), de Henar; búsqueda y ficha PDF (#8, Henar); equipo en PDF (#13, Jorge).
- **Pendiente:** API v2 (#14).

Leyenda: ✅ hecho · 🟡 a medias · ❌ falta
