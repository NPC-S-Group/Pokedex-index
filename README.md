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
| Autenticados | resto de `/pokedex` y `/teams` | 100 por minuto |
| Sistema | `GET /health` | sin límite |

**¿Por qué diferentes límites?** Porque el riesgo y el coste de cada endpoint son distintos. Los públicos no exigen token y son el objetivo natural de bots: el registro se usa una vez por persona y el login, unas pocas veces. Los que llaman a la PokeAPI consumen un servicio externo que no es nuestro y que también limita, así que no dejamos que un usuario lo agote. El resto es el uso normal de la API con un usuario identificado y puede ser más generoso.

**¿Cómo protege esto la API?** Frena los ataques de fuerza bruta contra el login (10 intentos por minuto en lugar de miles), la creación masiva de cuentas y el abuso de la PokeAPI a través de nuestra API. Además, cada endpoint tiene su propio contador: agotar la búsqueda en la PokeAPI no bloquea la Pokédex ni los equipos.

**¿Qué pasa si un usuario excede el límite?** Recibe `429 Too Many Requests` y la petición no se procesa. Ni siquiera se comprueba la contraseña: el límite se evalúa antes. Puede volver a intentarlo cuando pase la ventana de tiempo (un minuto o una hora).

> Nota técnica: no usamos `default_limits` de slowapi porque, con la versión de FastAPI del proyecto, no llega a aplicarse a las rutas de los routers. Por eso cada endpoint lleva su `@limiter.limit` explícito, y los tests de `tests/test_rate_limit_cors.py` comprueban cada nivel.

### CORS
Solo se aceptan los orígenes de `CORS_ORIGINS` (por defecto `http://localhost:5173`), los métodos que usa la API (GET, POST, PUT, PATCH y DELETE) y las cabeceras `Authorization` y `Content-Type`. Un navegador en otro origen no puede leer las respuestas.

## Metodología
Ramas `features/<nombre>` desde `develop`, integradas por pull request revisado por otro miembro. Commits con Conventional Commits.
