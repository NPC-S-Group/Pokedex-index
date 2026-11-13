# Pokédex API

![CI](https://github.com/NPC-S-Group/Pokedex-index/actions/workflows/ci.yml/badge.svg)

API REST con FastAPI que consume PokeAPI y permite a cada usuario gestionar su Pokédex y sus equipos de batalla. Práctica 1 de Sistemas de Información (UFV).

## Descripción
Cada usuario se registra, inicia sesión con un token JWT y gestiona su propia Pokédex: busca Pokémon en la [PokeAPI](https://pokeapi.co), los añade, marca cuáles ha capturado y cuáles son favoritos, consulta sus estadísticas y la exporta en CSV o PDF. También puede montar equipos de batalla de hasta 6 Pokémon de su Pokédex y descargarlos en PDF, con la ficha de cada uno y las estadísticas combinadas del equipo.

Stack: FastAPI, SQLModel (SQLite por defecto), JWT con `python-jose`, `bcrypt`, `slowapi`, `httpx` y `fpdf2`. Tests con `pytest` y CI con GitHub Actions.

## Equipo
| Miembro | Usuario Git | Partes desarrolladas |
|---|---|---|
| Jorge Aranda | [@jorgearanda179](https://github.com/jorgearanda179) | Organización, repo, tablero y CI (GitHub Actions + Docker); estructura base; fixtures comunes de tests; equipos de batalla y su export en PDF; rate limiting y CORS; documentación |
| Miguel Pina | [@miguelpina671-cmd](https://github.com/miguelpina671-cmd) | Autenticación (`/auth/me`) y sus tests; tests del CRUD de la Pokédex y fix de `capture_date`; export de la Pokédex en CSV/PDF; API v2 de ejemplo |
| Henar Oliva | [@henarolivaperez-lang](https://github.com/henarolivaperez-lang) | Cliente de PokeAPI (errores, timeouts y logging); middleware de logging; búsqueda, detalle y ficha en PDF; estadísticas ampliadas |

## Instalación
```bash
git clone https://github.com/NPC-S-Group/Pokedex-index.git
cd Pokedex-index
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuración
Copia `.env.example` como `.env` y rellena los valores:

| Variable | Para qué sirve |
|---|---|
| `SECRET_KEY` | **Obligatoria.** Clave para firmar los JWT. Genera una con `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DATABASE_URL` | Conexión a la base de datos (por defecto `sqlite:///./pokedex.db`) |
| `CORS_ORIGINS` | Orígenes permitidos para CORS, como lista JSON (por defecto `["http://localhost:5173"]`) |
| `POKEAPI_TIMEOUT` | Opcional. Segundos de espera a la PokeAPI antes de responder 504 (por defecto 5) |
| `LOG_LEVEL` | Opcional. Nivel de log: `DEBUG`, `INFO`, `WARNING` o `ERROR` (por defecto `INFO`) |

## Ejecución
**En local** (con el `.env` configurado):
```bash
uvicorn app.main:app --reload
```
La API queda en <http://localhost:8000> y la documentación interactiva (Swagger) en <http://localhost:8000/docs>. Para probar los endpoints protegidos: `POST /api/v1/auth/register`, después el botón **Authorize** con tu usuario y contraseña.

**Con Docker:**
```bash
docker build -t pokedex-api .
docker run --rm -p 8000:8000 --env-file .env pokedex-api
```
La imagen corre con un usuario sin privilegios y no incluye `.env` ni bases de datos (`.dockerignore`).

## Tests
```bash
pytest --cov=app --cov-report=term-missing
```

## Endpoints
Todos bajo `/api/v1` salvo `/health`. 🔒 = requiere `Authorization: Bearer <token>`.

| Método | Ruta | Qué hace | Límite |
|---|---|---|---|
| POST | `/auth/register` | Registro (contraseña con mayúscula y número, mínimo 8) | 5/hora |
| POST | `/auth/login` | Login (formulario OAuth2); devuelve el JWT | 10/min |
| GET 🔒 | `/auth/me` | Usuario actual | 100/min |
| GET 🔒 | `/pokemon/search?q=&type=&limit=&offset=` | Busca en la PokeAPI por nombre y/o tipo | 30/min |
| GET 🔒 | `/pokemon/{id_or_name}` | Detalle: tipos, habilidades, sprites y estadísticas | 30/min |
| GET 🔒 | `/pokemon/{id_or_name}/card` | Ficha del Pokémon en PDF | 30/min |
| POST 🔒 | `/pokedex` | Añade un Pokémon (valida que exista; sin duplicados) | 30/min |
| GET 🔒 | `/pokedex?captured=&favorite=&sort=&order=&limit=&offset=` | Lista tu Pokédex | 100/min |
| GET 🔒 | `/pokedex/stats` | Total, capturados, favoritos, % completado, tipo más común y racha | 100/min |
| GET 🔒 | `/pokedex/export?format=csv\|pdf` | Exporta la Pokédex con los mismos filtros | 10/min |
| GET · PATCH · DELETE 🔒 | `/pokedex/{entry_id}` | Detalle, actualización parcial y borrado de una entrada propia | 100/min |
| GET · POST 🔒 | `/teams` | Lista tus equipos · crea uno (1 a 6 Pokémon de tu Pokédex) | 100/min |
| GET · PUT · DELETE 🔒 | `/teams/{team_id}` | Detalle, reemplazo completo y borrado | 100/min |
| GET 🔒 | `/teams/{team_id}/export` | Equipo en PDF: estadísticas combinadas y fichas | 30/min |
| GET | `/health` | Estado de la API | — |

Errores comunes: `401` sin token o token inválido · `404` no existe o es de otro usuario · `409` duplicado · `422` datos no válidos · `429` límite superado · `502/504` la PokeAPI falla o no responde.

## Decisiones de Diseño

### Rate limiting
Cada endpoint tiene su límite (`app/limits.py`), contado por IP con `slowapi`:

| Tipo | Endpoints | Límite |
|---|---|---|
| Públicos | `POST /auth/register` | 5 por hora |
| | `POST /auth/login` | 10 por minuto |
| Llaman a la PokeAPI | `GET /pokemon/search`, `GET /pokemon/{id}`, `GET /pokemon/{id}/card` (PDF), `POST /pokedex`, `GET /teams/{id}/export` (PDF) | 30 por minuto |
| Exportar la Pokédex | `GET /pokedex/export` (CSV o PDF, sin llamar a la PokeAPI) | 10 por minuto |
| Autenticados | `GET /auth/me`, resto de `/pokedex` y `/teams` | 100 por minuto |
| Sistema | `GET /health` | sin límite |

**¿Por qué diferentes límites?** Porque el riesgo y el coste de cada endpoint son distintos. Los públicos no exigen token y son el objetivo natural de bots: el registro se usa una vez por persona y el login, unas pocas veces. Los que llaman a la PokeAPI consumen un servicio externo que no es nuestro y que también limita, así que no dejamos que un usuario lo agote. Exportar recorre toda la Pokédex y genera un fichero (el PDF, en memoria): es más caro que un GET normal y nadie necesita más de unas pocas descargas por minuto. El resto es el uso normal de la API con un usuario identificado y puede ser más generoso.

**¿Cómo protege esto la API?** Frena los ataques de fuerza bruta contra el login (10 intentos por minuto en lugar de miles), la creación masiva de cuentas y el abuso de la PokeAPI a través de nuestra API. Además, cada endpoint tiene su propio contador: agotar la búsqueda en la PokeAPI no bloquea la Pokédex ni los equipos.

**¿Qué pasa si un usuario excede el límite?** Recibe `429 Too Many Requests` y la petición no se procesa. Ni siquiera se comprueba la contraseña: el límite se evalúa antes. Puede volver a intentarlo cuando pase la ventana de tiempo (un minuto o una hora).

> Nota técnica: no usamos `default_limits` de slowapi porque, con la versión de FastAPI del proyecto, no llega a aplicarse a las rutas de los routers. Por eso cada endpoint lleva su `@limiter.limit` explícito, y los tests de `tests/test_rate_limit_cors.py` comprueban cada nivel.

### CORS
Solo se aceptan los orígenes de `CORS_ORIGINS` (por defecto `http://localhost:5173`), los métodos que usa la API (GET, POST, PUT, PATCH y DELETE) y las cabeceras `Authorization` y `Content-Type`. Un navegador en otro origen no puede leer las respuestas.

### Cliente de PokeAPI
Toda la comunicación con la PokeAPI pasa por `PokeAPIService` (`app/services/pokeapi_service.py`). Cada llamada queda registrada en el logger `pokedex_api.pokeapi` con la URL, el código y los milisegundos.

**¿Qué pasa si la PokeAPI falla?** Nuestra API nunca responde un 500 por culpa de un servicio externo. Cada fallo se traduce a un código que dice de quién es el problema:

| Qué pasa en la PokeAPI | Qué respondemos |
|---|---|
| El Pokémon o el tipo no existe | `404 Not Found` |
| Identificador vacío o con caracteres raros | `422` (sin llamar a la PokeAPI) |
| Tarda más que `POKEAPI_TIMEOUT` | `504 Gateway Timeout` |
| Sin conexión, responde 5xx o 429 | `502 Bad Gateway` |
| Responde algo que no es JSON o le faltan campos | `502 Bad Gateway` |

El 500 queda para los errores de nuestro propio código. Así, quien use la API distingue un fallo nuestro de uno de la PokeAPI.

**Respuesta simplificada:** de la respuesta de la PokeAPI solo se guarda lo que usamos: id, nombre, tipos, altura en metros, peso en kilos, habilidades, imágenes y las seis estadísticas base. Si falta un dato que no es imprescindible, como la imagen, sale `null` en vez de fallar.

**Antes de llamar fuera:** el identificador se pasa a minúsculas y sin espacios, y solo se aceptan letras, números y guiones. Un nombre como `../ditto` se rechaza con 422 sin hacer la petición.

### Búsqueda y ficha de Pokémon
| Endpoint | Qué hace |
|---|---|
| `GET /api/v1/pokemon/search?q=chu&type=electric&limit=20&offset=0` | Busca por parte del nombre y/o por tipo. Devuelve `{count, limit, offset, results: [{id, name, sprite}]}` ordenado por número |
| `GET /api/v1/pokemon/{id_or_name}` | Detalle: tipos, altura (m), peso (kg), habilidades (y si son ocultas), sprites y las seis estadísticas base |
| `GET /api/v1/pokemon/{id_or_name}/card` | Ficha en PDF (A5) con imagen, tipos, datos y barras de estadísticas |

**¿Cómo se busca si la PokeAPI no tiene búsqueda?** Se pide una vez la lista de todos los nombres (una sola llamada, ~1300 Pokémon) y se filtra en nuestro servidor. La lista se guarda en memoria 24 horas, porque casi nunca cambia: así buscar no gasta llamadas a la PokeAPI. Con `type` se usa `/type/{tipo}`, que ya trae solo los de ese tipo (también en caché).

**Ficha en PDF:** se genera con `fpdf2`, en memoria, sin guardar archivos. La imagen se descarga solo del repositorio oficial de sprites (`raw.githubusercontent.com`, por HTTPS y como mucho 2 MB): así la API no puede usarse para descargar cosas de otros sitios. Si la imagen falla, la ficha sale igual con el hueco «Sin imagen».

### Estadísticas de la Pokédex
`GET /api/v1/pokedex/stats` devuelve:

```json
{
  "total_pokemon": 4, "captured": 2, "favorites": 0, "completion_percentage": 50.0,
  "most_common_type": "normal", "capture_streak_days": 2
}
```

- **`most_common_type`:** el tipo que más se repite en toda tu Pokédex (capturados o no). Un Pokémon de dos tipos cuenta para los dos. Si hay empate, gana el primero por orden alfabético, para que el resultado no cambie según el orden de las filas. Con la Pokédex vacía, `null`.
- **`capture_streak_days`:** días seguidos, hasta hoy, en los que capturaste al menos un Pokémon. Si hoy aún no has capturado nada, la racha sigue viva desde ayer y solo se rompe cuando pasa un día entero sin capturas. Los días se cuentan en UTC.
- **Tipos guardados:** al añadir un Pokémon se guardan sus tipos (`pokemon_types`) junto al nombre y la imagen. Así `/stats` no llama a la PokeAPI. Las bases de datos creadas antes reciben la columna nueva al arrancar (`app/database.py`), sin borrar nada; sus entradas antiguas no tienen tipos y no cuentan para el tipo más común.

### Logging
Todo lo importante queda en el log (`app/logs.py`), separado por tipo para poder filtrarlo:

| Logger | Qué registra | Nivel |
|---|---|---|
| `pokedex_api.peticiones` | Una línea por petición: id, método, ruta, código, ms, usuario e IP | INFO (2xx/3xx), WARNING (4xx), ERROR (5xx y errores no controlados, con traza) |
| `pokedex_api.auth` | Registros, logins correctos y fallidos, tokens no válidos | INFO / WARNING |
| `pokedex_api.validacion` | Qué campos fallan en cada 422 y por qué | WARNING |
| `pokedex_api.limites` | Quién supera qué límite (429) | WARNING |
| `pokedex_api.pokeapi` | Llamadas a la PokeAPI y sus fallos | INFO / ERROR |

```
INFO pokedex_api.peticiones · [9f71ab0932f7] GET /api/v1/teams → 200 (8.4 ms) usuario='ash' ip=127.0.0.1
WARNING pokedex_api.auth · login fallido para 'ash'
WARNING pokedex_api.limites · [3c1d…] POST /api/v1/auth/login → 429 · límite 10 per 1 minute superado · usuario=anónimo ip=127.0.0.1
```

**¿Qué no se registra nunca?** Contraseñas, tokens, cuerpos de petición ni query strings. En los 422 se guarda qué campo falla, no el valor enviado (podría ser una contraseña). Los nombres de usuario se escriben con comillas y escapados, así que nadie puede colar un salto de línea y falsear una línea del log.

**Id de petición:** cada respuesta lleva la cabecera `X-Request-ID`, y el mismo id aparece en todas las líneas de esa petición. Si el cliente manda su propio id (solo letras, números y guiones), se reutiliza.

El nivel se cambia con `LOG_LEVEL` en el `.env` (`DEBUG`, `INFO`, `WARNING` o `ERROR`).

### Versionado de la API
Las rutas llevan la versión en la URL (`/api/v1/...`, `/api/v2/...`). Como ejemplo, `/api/v2/pokedex` ofrece los mismos datos que la v1 con otro contrato:

| | v1 (`GET /api/v1/pokedex`) | v2 (`GET /api/v2/pokedex`) |
|---|---|---|
| Respuesta del listado | Lista suelta de entradas | Sobre `{items, total, limit, offset, has_more}` |
| Datos del Pokémon | `pokemon_id`, `pokemon_name`, `pokemon_sprite` sueltos | Agrupados en `pokemon: {id, name, sprite}` |
| Captura | `is_captured`, `capture_date` | `captured`, `captured_at` |

**¿Por qué una v2 y no cambiar la v1?** Estos cambios rompen a cualquier cliente que ya use la v1: esperaba una lista y ahora recibe un objeto, y los campos cambian de nombre. Con la versión en la URL, los clientes antiguos siguen funcionando con la v1 y los nuevos usan la v2 cuando quieran. El sobre resuelve una carencia real de la v1, que no dice cuántas entradas hay en total ni si quedan más páginas.

**¿Cómo está hecha?** La v2 (`app/routers/pokedex_v2.py`) solo tiene lectura (listado y detalle) y reutiliza de la v1 los filtros, el orden y la comprobación de propiedad. Lo único que cambia es cómo se presenta la respuesta (`PokedexEntryV2` y `PokedexPageV2` en `app/models.py`), así que no hay lógica duplicada que pueda divergir. Escribir se sigue haciendo por la v1.

## Metodología
Ramas `features/<nombre>` desde `develop`, integradas por pull request revisado por otro miembro. Commits con Conventional Commits.

## Flujo de trabajo y despliegue
- **Ramas:** `main` (versiones entregables) ← `develop` (integración) ← `features/<nombre>` (una por tarea, con sus tests).
- **Pull requests:** todo entra en `develop` por PR revisado y aprobado por otro miembro. Las versiones pasan a `main` con un PR `develop → main`, una etiqueta y una release (`v0.5.0`, `v1.0.0`).
- **Tablero:** issues por tarea en un GitHub Project con columnas Por hacer / En curso / Hecho, fechas (vista Roadmap) e hitos.
- **CI** (`.github/workflows/ci.yml`): en cada push y PR a `main` o `develop`, tests con cobertura mínima del 80 % en GitHub y, si `HOMELAB_RUNNER=true`, construcción de la imagen Docker y prueba de arranque en un runner propio.
- **Despliegue:** la imagen Docker está lista y probada en el CI. No se ha desplegado en una plataforma pública (ver *Mejoras futuras*).

## Otras decisiones de diseño
- **404 y no 403 con lo ajeno:** si una entrada o un equipo es de otro usuario, respondemos como si no existiera, para no confirmar qué ids hay.
- **Equipos:** se guardan las entradas de la Pokédex, no los ids sueltos de la PokeAPI, así que solo se pueden usar Pokémon que tienes. La posición sigue el orden enviado y `PUT` reemplaza el equipo entero. Borrar un Pokémon de la Pokédex lo saca de sus equipos.
- **PokeAPI aislada en un servicio** (`app/services/pokeapi_service.py`) que se inyecta como dependencia: los routers no saben de `httpx` y los tests la sustituyen por una falsa, sin salir a internet.
- **Un solo generador de PDF** (`fpdf2`, Python puro): la ficha del Pokémon se reutiliza en el PDF del equipo.
- **`bcrypt` directo en lugar de `passlib`:** `passlib` lleva años sin mantenerse y falla con `bcrypt >= 4.1`.
- **Límites explícitos en cada endpoint:** `default_limits` de slowapi no se aplica a las rutas de los routers con esta versión de FastAPI (lo detectaron los tests), así que cada endpoint declara su `@limiter.limit`.

## Decisiones de Seguridad
- **Contraseñas** con `bcrypt` (sal por usuario). Nunca se devuelven ni se registran en los logs.
- **JWT** firmados con HS256 y `SECRET_KEY`, con caducidad de 24 horas. Sin `SECRET_KEY` la aplicación no arranca: no hay clave por defecto.
- **Login sin pistas:** el mismo mensaje para "no existe el usuario" y "contraseña incorrecta".
- **Validación de entrada** con Pydantic (longitudes, rangos, contraseña robusta, máximo 6 por equipo). Los identificadores de Pokémon se validan antes de llamar fuera, y el orden (`sort`) se traduce a columna con una lista cerrada, nunca se pega en el SQL.
- **Rate limiting** por tipo de endpoint y **CORS** limitado a los orígenes de `CORS_ORIGINS`.
- **Secretos fuera del repo:** `.env` en `.gitignore` y `.dockerignore`. El CI usa claves de prueba.
- **Contenedor** con usuario sin privilegios.
- **Imágenes de las fichas** solo desde `raw.githubusercontent.com`, por HTTPS y hasta 2 MB: la API no se puede usar para hacer peticiones a otros sitios (SSRF).
- **Logs sin datos sensibles:** ni contraseñas, ni tokens, ni cuerpos de petición, ni query strings. Los nombres de usuario se escapan para que nadie pueda inventar líneas en el log.
- Detalle y limitaciones conocidas en [`SECURITY.md`](SECURITY.md).

## Mejoras Futuras
- Desplegar la imagen en una plataforma (Render, Railway o Fly.io) con PostgreSQL.
- Revocar tokens (lista de bloqueo o tokens de refresco cortos).
- Rate limiting por usuario y con almacenamiento compartido (Redis), en lugar de por IP y en memoria.
- Migraciones de base de datos con Alembic.
- Caché de las respuestas de la PokeAPI más allá de la búsqueda.
