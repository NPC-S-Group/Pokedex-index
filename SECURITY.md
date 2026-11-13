# Seguridad · Pokédex API

## Cómo informar de un problema
Si encuentras una vulnerabilidad, **no abras una issue pública**. Escribe directamente a cualquiera de los miembros del equipo (ver la tabla *Equipo* del README) con los pasos para reproducirla. Responderemos y lo corregiremos en una rama `fix/` antes de documentarlo.

## Medidas aplicadas

| Riesgo | Medida | Dónde |
|---|---|---|
| Robo de contraseñas | Hash con `bcrypt` y sal por usuario. Nunca se devuelven ni aparecen en los logs | `app/auth.py`, `app/logs.py` |
| Contraseñas débiles | Mínimo 8 caracteres, con al menos una mayúscula y un número | `UserCreate` en `app/models.py` |
| Suplantación | JWT firmados (HS256) con caducidad de 24 h. Sin `SECRET_KEY` la app no arranca | `app/auth.py`, `app/config.py` |
| Enumeración de usuarios | El mismo error para usuario inexistente y contraseña incorrecta | `app/routers/auth.py` |
| Token de una cuenta borrada o desactivada | Cada petición busca al usuario por el `user_id` del token y comprueba `is_active`. Todos los fallos del token responden el mismo `401`, sin decir cuál ha fallado | `app/dependencies.py` |
| Cuentas o entradas duplicadas por peticiones simultáneas | Restricciones `UNIQUE` en la base de datos (usuario, email, Pokémon por usuario). Si salta una, se deshace la transacción y se responde 409 | `app/models.py`, routers `auth`, `pokedex` |
| Acceso a datos ajenos | Cada consulta filtra por el usuario del token. Lo ajeno responde 404, sin confirmar que existe | routers `pokedex`, `teams` |
| Fuerza bruta y abuso | Rate limiting: registro 5/h, login 10/min, PokeAPI 30/min, export 10/min, resto 100/min | `app/limits.py` |
| Inyección SQL | Consultas con SQLModel/SQLAlchemy parametrizadas. El orden (`sort`) sale de una lista cerrada | `app/routers/pokedex.py` |
| Entradas maliciosas | Validación con Pydantic. Los identificadores de Pokémon se validan antes de llamar a la PokeAPI | `app/models.py`, `app/services/pokeapi_service.py` |
| Uso desde webs ajenas | CORS limitado a `CORS_ORIGINS` y a los métodos y cabeceras que usa la API | `app/main.py` |
| Fallos de un servicio externo | Timeout y traducción de errores de la PokeAPI a 502/504, sin trazas internas | `app/services/pokeapi_service.py` |
| Fuga de secretos | `.env` en `.gitignore` y `.dockerignore`. El CI usa claves de prueba. Historial revisado sin secretos | raíz del repo |
| Contenedor comprometido | La imagen corre con un usuario sin privilegios (`api`) | `Dockerfile` |
| Peticiones a otros sitios desde el servidor (SSRF) | Las imágenes de las fichas en PDF solo se descargan de `raw.githubusercontent.com`, por HTTPS y hasta 2 MB. Se compara el host exacto: `raw.githubusercontent.com.evil.com` se rechaza | `app/services/pokeapi_service.py` |
| Datos sensibles en los logs | No se registran contraseñas, tokens, cuerpos de petición ni query strings. En los 422 solo se guarda qué campo falla, nunca el valor enviado | `app/logs.py` |
| Falsear líneas del log (log injection) | Los nombres de usuario se escriben con `%r`, con los saltos de línea escapados. Un `X-Request-ID` del cliente solo se reutiliza si son letras, números y guiones | `app/logs.py`, `app/routers/auth.py` |
| Inyección en la cabecera de descarga | El nombre del fichero de la ficha se limpia antes de ponerlo en `Content-Disposition`. La exportación de la Pokédex usa un nombre fijo (`pokedex.csv` o `pokedex.pdf`) | `app/routers/pokemon.py`, `app/routers/pokedex.py` |
| Fórmulas en el CSV exportado (CSV injection) | Las celdas que empiezan por `=`, `+`, `-`, `@`, tabulador o retorno de carro llevan una comilla delante, para que Excel o LibreOffice no las ejecuten al abrir el fichero | `app/services/export_service.py` |
| Ficheros en el servidor | Los PDF se generan en memoria y se envían sin escribir nada en disco | `app/services/ficha_pdf.py` |

## Gestión de secretos
- La configuración se lee de variables de entorno o de `.env` (ver `.env.example`). **El `.env` real nunca se sube**: un secreto subido queda en el historial aunque se borre después.
- En producción, `SECRET_KEY` debe ser larga y aleatoria (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) y distinta en cada entorno.
- Si una clave se filtra: cámbiala (esto invalida todos los tokens emitidos) y revisa el historial.

## Limitaciones conocidas
- **Los tokens no se pueden revocar** antes de que caduquen: cerrar sesión solo borra el token en el cliente.
- **El rate limiting es por IP y en memoria:** se reinicia al reiniciar la app, no se comparte entre varias instancias y varios usuarios detrás de la misma IP comparten límite.
- **SQLite** es para desarrollo y la práctica. En producción convendría PostgreSQL.
- **La caché de la búsqueda de Pokémon** (24 h) está en memoria: se pierde al reiniciar y no se comparte entre varias instancias.
- Las dependencias se instalan con versiones mínimas (`>=`) en `requirements.txt`. `uv.lock` fija las versiones exactas para quien use `uv`.
