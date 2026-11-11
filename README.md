# Pokédex API

API REST con FastAPI que consume PokeAPI y permite a cada usuario gestionar su Pokédex y sus equipos de batalla. Práctica 1 de Sistemas de Información (UFV).

## Descripción
_Pendiente._

## Equipo
| Miembro | Usuario Git | Partes desarrolladas |
|---|---|---|
| Jorge Aranda | [@jorgearanda179](https://github.com/jorgearanda179) | _Pendiente_ |
| Miguel Pina | [@miguelpina671-cmd](https://github.com/miguelpina671-cmd) | _Pendiente_ |
| Henar Oliva | [@henarolivaperez-lang](https://github.com/henarolivaperez-lang) | _Pendiente_ |

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
| `SECRET_KEY` | Clave para firmar los tokens JWT |
| `DATABASE_URL` | Cadena de conexión a la base de datos |

## Ejecución
_Pendiente._

## Tests
```bash
pytest --cov=app --cov-report=term-missing
```

## Decisiones de Diseño

### Rate limiting
Cada endpoint tiene su límite (`app/limits.py`), contado por IP con `slowapi`:

| Tipo | Endpoints | Límite |
|---|---|---|
| Públicos | `POST /auth/register` | 5 por hora |
| | `POST /auth/login` | 10 por minuto |
| Llaman a la PokeAPI | `GET /pokemon/{id}`, `POST /pokedex` | 30 por minuto |
| Autenticados | `GET /auth/me`, resto de `/pokedex` y `/teams` | 100 por minuto |
| Sistema | `GET /health` | sin límite |

**¿Por qué diferentes límites?** Porque el riesgo y el coste de cada endpoint son distintos. Los públicos no exigen token y son el objetivo natural de bots: el registro se usa una vez por persona y el login, unas pocas veces. Los que llaman a la PokeAPI consumen un servicio externo que no es nuestro y que también limita, así que no dejamos que un usuario lo agote. El resto es el uso normal de la API con un usuario identificado y puede ser más generoso.

**¿Cómo protege esto la API?** Frena los ataques de fuerza bruta contra el login (10 intentos por minuto en lugar de miles), la creación masiva de cuentas y el abuso de la PokeAPI a través de nuestra API. Además, cada endpoint tiene su propio contador: agotar la búsqueda en la PokeAPI no bloquea la Pokédex ni los equipos.

**¿Qué pasa si un usuario excede el límite?** Recibe `429 Too Many Requests` y la petición no se procesa. Ni siquiera se comprueba la contraseña: el límite se evalúa antes. Puede volver a intentarlo cuando pase la ventana de tiempo (un minuto o una hora).

> Nota técnica: no usamos `default_limits` de slowapi porque, con la versión de FastAPI del proyecto, no llega a aplicarse a las rutas de los routers. Por eso cada endpoint lleva su `@limiter.limit` explícito, y los tests de `tests/test_rate_limit_cors.py` comprueban cada nivel.

### CORS
Solo se aceptan los orígenes de `CORS_ORIGINS` (por defecto `http://localhost:5173`), los métodos que usa la API (GET, POST, PUT, PATCH y DELETE) y las cabeceras `Authorization` y `Content-Type`. Un navegador en otro origen no puede leer las respuestas.

### Búsqueda y ficha de Pokémon
| Endpoint | Qué hace |
|---|---|
| `GET /api/v1/pokemon/search?q=chu&type=electric&limit=20&offset=0` | Busca por parte del nombre y/o por tipo. Devuelve `{count, limit, offset, results: [{id, name, sprite}]}` ordenado por número |
| `GET /api/v1/pokemon/{id_or_name}` | Detalle: tipos, altura (m), peso (kg), habilidades (y si son ocultas), sprites y las seis estadísticas base |
| `GET /api/v1/pokemon/{id_or_name}/card` | Ficha en PDF (A5) con imagen, tipos, datos y barras de estadísticas |

**¿Cómo se busca si la PokeAPI no tiene búsqueda?** Se pide una vez la lista de todos los nombres (una sola llamada, ~1300 Pokémon) y se filtra en nuestro servidor. La lista se guarda en memoria 24 horas, porque casi nunca cambia: así buscar no gasta llamadas a la PokeAPI. Con `type` se usa `/type/{tipo}`, que ya trae solo los de ese tipo (también en caché).

**Ficha en PDF:** se genera con `fpdf2`, en memoria, sin guardar archivos. La imagen se descarga solo del repositorio oficial de sprites (`raw.githubusercontent.com`, por HTTPS y como mucho 2 MB): así la API no puede usarse para descargar cosas de otros sitios. Si la imagen falla, la ficha sale igual con el hueco «Sin imagen».

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

## Metodología
Ramas `features/<nombre>` desde `develop`, integradas por pull request revisado por otro miembro. Commits con Conventional Commits.
