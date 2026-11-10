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

## Metodología
Ramas `features/<nombre>` desde `develop`, integradas por pull request revisado por otro miembro. Commits con Conventional Commits.
