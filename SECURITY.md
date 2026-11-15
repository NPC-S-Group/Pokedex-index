# Seguridad · Pokédex API

## Cómo informar de un problema
Si encuentras una vulnerabilidad, **no abras una issue pública**. Escribe directamente a cualquiera de los miembros del equipo (ver la tabla *Equipo* del README) con los pasos para reproducirla. Responderemos y lo corregiremos en una rama `fix/` antes de documentarlo.

## Medidas aplicadas

| Riesgo | Medida | Dónde |
|---|---|---|
| Robo de contraseñas | Hash con `bcrypt` y sal por usuario. Nunca se devuelven ni aparecen en los logs | `app/auth.py`, `app/logs.py` |
| Contraseñas débiles | Mínimo 8 caracteres, con al menos una mayúscula y un número | `UserCreate` en `app/models.py` |
| Contraseñas de más de 72 bytes (antes daban error 500) | `bcrypt` solo admite 72 bytes. El registro las rechaza con 422 (se cuentan bytes: `ñ` o una tilde ocupan 2) y el login responde el 401 de siempre, ejecutando igualmente bcrypt para no cambiar el tiempo | `app/contrasenas.py`, `app/auth.py`, `app/models.py` |
| Suplantación | JWT firmados (HS256): el de acceso caduca a los 30 min y el refresh token a los 7 días, con rotación y logout. Sin `SECRET_KEY`, con menos de 32 caracteres o con la de `.env.example`, la app no arranca | `app/auth.py`, `app/config.py` |
| Robo de un refresh token | Duran 7 días y son de un solo uso (rotación). Si se reutiliza uno ya usado, se anulan todos los de la cuenta. El logout lo anula. Un refresh token no sirve para entrar, ni un access token para renovar | `app/routers/auth.py`, `app/dependencies.py` |
| Cuentas duplicadas o suplantadas con mayúsculas (`Ash`/`ash`, `ASH@x.com`/`ash@x.com`) | El email se guarda en minúsculas y el usuario se compara sin mayúsculas, con un índice único sobre `lower(username)`. El usuario solo admite letras, números y `_ . -` | `app/models.py`, `app/routers/auth.py` |
| Enumeración de usuarios | El mismo error (401, mismo mensaje y mismas cabeceras) para usuario inexistente, contraseña incorrecta y cuenta desactivada. Además, el mismo tiempo de respuesta: `bcrypt` se ejecuta siempre, con un hash falso si el usuario no existe, para que un atacante no pueda distinguir los casos con un cronómetro (timing attack). Lo comprueban tests en `tests/test_auth.py` | `app/routers/auth.py` |
| Token de una cuenta borrada o desactivada | Cada petición busca al usuario por el `user_id` del token y comprueba `is_active`. Todos los fallos del token responden el mismo `401`, sin decir cuál ha fallado | `app/dependencies.py` |
| Cuentas o entradas duplicadas por peticiones simultáneas | Restricciones `UNIQUE` en la base de datos (usuario, email, Pokémon por usuario). Si salta una, se deshace la transacción y se responde 409 | `app/models.py`, routers `auth`, `pokedex` |
| Acceso a datos ajenos | Cada consulta filtra por el usuario del token. Lo ajeno responde 404, sin confirmar que existe | routers `pokedex`, `teams` |
| Fuerza bruta y abuso | Rate limiting por IP: registro 5/h, login 10/min, PokeAPI 30/min, export 10/min, resto 100/min | `app/limits.py` |
| Fuerza bruta contra una cuenta cambiando de IP | Además del límite por IP, 5 logins fallidos en 15 min bloquean esa cuenta (429 con `Retry-After`), aunque luego llegue la contraseña buena. Cuenta también para usuarios que no existen, para no delatar cuáles existen. Un login correcto pone el contador a cero | `app/limits.py`, `app/routers/auth.py` |
| Todos los usuarios con la misma IP detrás del proxy de Render | Con `TRUSTED_PROXY_HOPS=1` se usa la IP real del cliente de `X-Forwarded-For`, contando **desde la derecha** (la que añade Render), no la de la izquierda, que el cliente puede inventarse | `app/limits.py`, `app/logs.py` |
| Inyección SQL | Consultas con SQLModel/SQLAlchemy parametrizadas. El orden (`sort`) sale de una lista cerrada | `app/routers/pokedex.py` |
| Entradas maliciosas | Validación con Pydantic. Los identificadores de Pokémon se validan antes de llamar a la PokeAPI | `app/models.py`, `app/services/pokeapi_service.py` |
| Uso desde webs ajenas | CORS limitado a `CORS_ORIGINS` y a los métodos y cabeceras que usa la API | `app/main.py` |
| Fallos de un servicio externo | Timeout y traducción de errores de la PokeAPI a 502/504, sin trazas internas | `app/services/pokeapi_service.py` |
| Fuga de secretos | `.env` en `.gitignore` y `.dockerignore`. El CI usa claves de prueba. Historial revisado sin secretos | raíz del repo |
| Robo del token en la red | En producción, la API se sirve solo por HTTPS (Render pone el certificado y redirige HTTP a HTTPS). Sin HTTPS, el token y la contraseña del login viajarían en claro | despliegue en Render |
| Ataques desde el navegador (clickjacking, *MIME sniffing*, fugas por `Referer`, tokens en caché) | Cabeceras en todas las respuestas: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Strict-Transport-Security` y `Content-Security-Policy` (salvo en `/docs` y `/redoc`, que cargan Swagger de un CDN). `/api/v1/auth` responde con `Cache-Control: no-store` | `app/seguridad.py` |
| Dependencias que cambian solas | `requirements.txt` y `requirements-dev.txt` con versiones exactas (`==`), generadas desde `uv.lock`. La imagen de Docker no lleva las de tests | raíz del repo |
| Contenedor comprometido | La imagen corre con un usuario sin privilegios (`api`) | `Dockerfile` |
| Peticiones a otros sitios desde el servidor (SSRF) | Las imágenes de las fichas en PDF solo se descargan de `raw.githubusercontent.com`, por HTTPS y hasta 2 MB. Se compara el host exacto: `raw.githubusercontent.com.evil.com` se rechaza | `app/services/pokeapi_service.py` |
| Datos sensibles en los logs | No se registran contraseñas, tokens, cuerpos de petición ni query strings. En los 422 solo se guarda qué campo falla, nunca el valor enviado | `app/logs.py` |
| Falsear líneas del log (log injection) | Los nombres de usuario se escriben con `%r`, con los saltos de línea escapados. Un `X-Request-ID` del cliente solo se reutiliza si son letras, números y guiones | `app/logs.py`, `app/routers/auth.py` |
| Inyección en la cabecera de descarga | El nombre del fichero de la ficha se limpia antes de ponerlo en `Content-Disposition`. La exportación de la Pokédex usa un nombre fijo (`pokedex.csv` o `pokedex.pdf`) | `app/routers/pokemon.py`, `app/routers/pokedex.py` |
| Fórmulas en el CSV exportado (CSV injection) | Las celdas que empiezan por `=`, `+`, `-`, `@`, tabulador o retorno de carro llevan una comilla delante, para que Excel o LibreOffice no las ejecuten al abrir el fichero | `app/services/export_service.py` |
| Ficheros en el servidor | Los PDF se generan en memoria y se envían sin escribir nada en disco | `app/services/ficha_pdf.py` |

## Gestión de secretos
- La configuración se lee de variables de entorno o de `.env` (ver `.env.example`). **El `.env` real nunca se sube**: un secreto subido queda en el historial aunque se borre después.
- En producción, `SECRET_KEY` debe ser larga y aleatoria (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) y distinta en cada entorno. La app exige **32 caracteres como mínimo**: con una clave corta, quien tenga un token puede probar claves por fuerza bruta en su ordenador y, si la encuentra, firmar tokens de cualquier usuario.
- Si una clave se filtra: cámbiala (esto invalida todos los tokens emitidos) y revisa el historial.

## Limitaciones conocidas
- **El registro sí revela si un usuario o email ya existe** (`409`). El login no (mismo mensaje y mismo tiempo), pero el registro sí: si alguien intenta registrarse con tu email, sabrá que tienes cuenta. La solución real es **verificar el email por correo** (responder siempre «te hemos enviado un correo» y avisar allí de que ya existe), que necesita un servidor de correo y queda fuera de la práctica. Mientras, lo frena el límite de 5 registros por hora por IP.
- **El access token no se puede anular** antes de que caduque (máximo 24 h): el logout anula el refresh token, pero el access token sigue valiendo hasta su caducidad y el cliente debe borrarlo.
- **Los refresh tokens caducados se borran** al arrancar la app y, los de cada usuario, cada vez que entra o renueva. Los anulados pero aún no caducados se guardan hasta que caducan: así se detecta si alguien reutiliza uno robado.
- **El rate limiting es en memoria:** se reinicia al reiniciar la app y no se comparte entre varias instancias (haría falta Redis). Varios usuarios detrás de la misma IP pública (una universidad, una empresa) comparten el límite por IP.
- **`TRUSTED_PROXY_HOPS` tiene que coincidir con la realidad.** Si se pone a 1 sin proxy delante, cualquiera puede elegir su IP con la cabecera `X-Forwarded-For` y saltarse el límite por IP (el límite por cuenta sigue funcionando). Si se pone a 0 detrás de Render, todos comparten la IP del proxy.
- **El bloqueo por cuenta lo puede provocar otro:** quien sepa tu nombre de usuario puede fallar 5 veces y dejarte sin entrar 15 minutos. Es el precio de frenar la fuerza bruta; los bloqueos quedan en el log.
- **SQLite** es para desarrollo y la práctica. En producción convendría PostgreSQL.
- **La caché de la búsqueda de Pokémon** (24 h) está en memoria: se pierde al reiniciar y no se comparte entre varias instancias.
