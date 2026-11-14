# `scripts/` · utilidades fuera de la API

No forman parte de la aplicación: no se copian en la imagen Docker ni cuentan para la cobertura.

| Archivo | Qué hace | Cuándo se usa | Tarea |
|---|---|---|---|
| `prueba_humo.py` | Prueba de humo de la API **desplegada**: registro y login, refresh tokens, PokeAPI real, Pokédex, estadísticas, exportar, v2, equipos, aislamiento entre usuarios y CORS (unas 50 comprobaciones). Borra lo que crea | Automáticamente en el CI después de cada despliegue en Render (trabajo `deploy-render`) y a mano antes de la entrega o de la defensa | #15 Miguel |

## Uso
```bash
python scripts/prueba_humo.py                         # contra Render
python scripts/prueba_humo.py http://localhost:8000   # contra la API en local
```
Sale con código 0 si todo va bien y con 1 si falla algo. Para qué sirve, por qué hace falta además de `pytest` y cuándo la hemos usado: README principal, *Tests → Prueba de humo del despliegue*.
