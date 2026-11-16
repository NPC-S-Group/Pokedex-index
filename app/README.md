# `app/` · código de la API

Paquete principal de la Pokédex API (FastAPI + SQLModel).

| Archivo | Qué hace | Estado |
|---|---|---|
| `main.py` | Crea la app: CORS, rate limiting, logging, routers bajo `/api/v1` (y la v2 de ejemplo bajo `/api/v2`) y `/health` | ✅ |
| `logs.py` | Middleware de logging de peticiones y registro de 422 y 429 (ver «Logging» en el README) | ✅ (#10) |
| `config.py` | Lee `.env` en un objeto `Settings` validado. La app no arranca sin una `SECRET_KEY` de al menos 32 caracteres (y distinta de la de ejemplo) | ✅ |
| `database.py` | Motor de la BD y una sesión por petición (`get_session`) | ✅ |
| `models.py` | Tablas (`User`, `RefreshToken`, `PokedexEntry`, `Team`, `TeamMember`) y esquemas de entrada y salida (`*Create`, `*Read`, `*Update`, y `*V2` de la API v2) | ✅ |
| `auth.py` | Hash de contraseñas con bcrypt y creación y lectura de JWT (HS256 = HMAC-SHA256): access token (30 min) y refresh token (7 días) | ✅ (#4) |
| `contrasenas.py` | Límite de 72 bytes de las contraseñas (el de bcrypt): más largas daban un 500 | ✅ (seguridad) |
| `dependencies.py` | Dependencias comunes: `SessionDep`, `CurrentUser` (usuario del token) y `ServicioPokeAPI` | ✅ |
| `limits.py` | Limitador de slowapi: cinco niveles por IP (con la IP real detrás del proxy de Render, `TRUSTED_PROXY_HOPS`) y el bloqueo por cuenta (5 logins fallidos en 15 min) | ✅ (#9, seguridad) |
| `seguridad.py` | Cabeceras de seguridad en todas las respuestas: `nosniff`, `X-Frame-Options`, `Referrer-Policy`, CSP y, por HTTPS, HSTS | ✅ (seguridad) |
| `versionado.py` | Deprecación de las rutas de la v1 con sucesora en la v2: cabeceras `Deprecation`, `Sunset` y `Link`, log de cada uso y `410 Gone` desde la fecha de retirada | ✅ (mejora de #14) |
| `routers/` | Endpoints, un archivo por grupo ([ver README](routers/README.md)) | ✅ |
| `services/` | PokeAPI, PDF, exportación y estadísticas ([ver README](services/README.md)) | ✅ |

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
