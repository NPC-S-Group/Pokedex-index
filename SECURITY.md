# Consideraciones de Seguridad · Pokédex API

## Cómo informar de un problema
Si encuentras una vulnerabilidad, **no abras una issue pública**. Escribe directamente a cualquiera de los miembros del equipo (ver la tabla *Equipo* del README) con los pasos para reproducirla. Responderemos y lo corregiremos en una rama `fix/` antes de documentarlo.

## Autenticación
- **JWT firmados con HS256**, es decir, **HMAC con SHA-256**: el servidor calcula un SHA-256 de la cabecera y la carga útil mezclado con `SECRET_KEY`. Si alguien cambia un solo carácter del token, la firma deja de cuadrar y se rechaza con `401`. Es el algoritmo que se usa en la práctica guiada (clave secreta compartida; RS256 haría falta solo si otros servicios tuvieran que validar sin poder emitir).
- **Dos tokens:**
  - El **access token** va en cada petición (`Authorization: Bearer …`) y caduca a los **30 minutos**.
  - El **refresh token** solo sirve en `/auth/refresh` y `/auth/logout`, caduca a los **7 días** y es **de un solo uso** (rotación).
  - Cada uno lleva `type` y no sirve en lugar del otro.
- **Política de expiración:** el access token es corto a propósito. No se puede anular antes de que caduque (se valida sin consultar la base de datos), así que tras un logout o un robo deja de valer en 30 minutos como mucho. Si se reutiliza un refresh token ya usado (señal de robo), se anulan todos los de esa cuenta.
- **Cada petición protegida** comprueba la firma y la caducidad, busca al usuario por el `user_id` del token y comprueba que sigue activo. Cualquier fallo responde el mismo `401`, sin decir cuál ha fallado.
- **Login sin pistas:** el mismo mensaje, el mismo código y el **mismo tiempo de respuesta** para «el usuario no existe», «contraseña incorrecta» y «cuenta desactivada». bcrypt se ejecuta siempre, con un hash falso si el usuario no existe, para que no se pueda distinguir con un cronómetro.
- **Mayúsculas:** `Ash`, `ash` y `ASH` son la misma cuenta (índice único sobre `lower(username)`), y el email se guarda en minúsculas. Así nadie puede crear una cuenta casi igual que otra para hacerse pasar por ella.

## Contraseñas
- **Algoritmo: bcrypt**, con una sal aleatoria por usuario y coste 12 (lento a propósito: cada intento cuesta ~250 ms).
- **No SHA-256 a secas:** SHA-256 está pensado para ser muy rápido, así que con una tarjeta gráfica se prueban miles de millones de contraseñas por segundo. bcrypt existe precisamente para que eso sea inviable.
- **Política:** mínimo 8 caracteres, con al menos una mayúscula y un número, y **como mucho 72 bytes**. bcrypt solo usa los primeros 72 bytes y bcrypt ≥ 5 da error con más: sin este límite, una contraseña larga provocaba un `500` en el registro y en el login. Ahora el registro la rechaza con `422` y el login la trata como incorrecta (`401`), ejecutando igualmente bcrypt para tardar lo mismo. La regla está en un solo sitio, `app/contrasenas.py`.
- Se guarda **solo el hash**. La contraseña nunca se devuelve (`UserRead` no tiene ese campo) ni aparece en los logs.

## Rate Limiting
| Tipo | Endpoints | Límite | Por qué |
|---|---|---|---|
| Registro | `POST /auth/register` | 5 por hora | Frena la creación masiva de cuentas y la prueba de emails (ver *Limitaciones*) |
| Login y tokens | `POST /auth/login`, `/auth/refresh`, `/auth/logout` | 10 por minuto | Fuerza bruta de contraseñas |
| Login, **por cuenta** | `POST /auth/login` con contraseña incorrecta | 5 fallos cada 15 minutos | Fuerza bruta contra una cuenta cambiando de IP |
| Llaman a la PokeAPI | búsqueda, detalle, ficha, `POST /pokedex`, PDF del equipo | 30 por minuto | No agotar un servicio externo que no es nuestro |
| Exportar | `GET /pokedex/export` | 10 por minuto | Recorre toda la Pokédex y genera un fichero |
| Resto autenticados | Pokédex, equipos, `/auth/me`, v2 | 100 por minuto | Uso normal |

- Superar el límite responde **`429`** sin procesar la petición (en el login, ni siquiera se comprueba la contraseña) y queda en el log.
- **IP real detrás de un proxy:** en Render, todas las conexiones llegan desde su proxy. Con esa IP, todos los usuarios compartían el mismo contador (10 logins fallidos de uno bloqueaban a todos). Con **`TRUSTED_PROXY_HOPS=1`** o su atajo **`TRUST_PROXY=true`** (solo en Render) se usa la **última** IP de `X-Forwarded-For`, la que añade el proxy, y no la primera, que la puede inventar el cliente para saltarse el límite. Si algún día hubiera dos proxies (p. ej. Cloudflare delante de Render), se pondría `2` y se cogería la penúltima. Con `0` (local, homelab) se usa la IP de la conexión. Los logs usan la misma IP.
- **Límite por cuenta:** el límite por IP se salta usando muchas IPs. Por eso, tras 5 contraseñas incorrectas en 15 minutos, esa cuenta responde `429` (con `Retry-After: 900`) aunque luego llegue la contraseña buena, venga de la IP que venga. Cuenta también para usuarios que no existen (si no, el `429` delataría cuáles existen) y no distingue mayúsculas. Un login correcto pone el contador a cero y las demás cuentas no se ven afectadas.

## CORS
- **Orígenes permitidos:** solo los de `CORS_ORIGINS` (por defecto `http://localhost:5173`, el típico de un frontend en desarrollo). Métodos: GET, POST, PUT, PATCH y DELETE. Cabeceras: `Authorization` y `Content-Type`.
- **Por qué hace falta:** sin CORS, cualquier web que visite un usuario podría llamar a nuestra API desde su navegador y leer las respuestas. Con CORS, el navegador solo deja leerlas a los orígenes de la lista. Swagger (`/docs`) no lo necesita porque se sirve desde el mismo origen que la API.

## Variables de Entorno
| Variable | ¿Sensible? | Qué guarda |
|---|---|---|
| `SECRET_KEY` | **Sí, la más crítica** | Firma los tokens: quien la tenga puede hacerse pasar por cualquier usuario |
| `DATABASE_URL` | Sí, si lleva usuario y contraseña (PostgreSQL) | Conexión a la base de datos |
| `CORS_ORIGINS`, `POKEAPI_TIMEOUT`, `LOG_LEVEL`, `LOG_FILE`, `TRUSTED_PROXY_HOPS` | No | Configuración |

**Cómo se protegen:**
- Se leen del entorno o de `.env`. **El `.env` real nunca se sube**: está en `.gitignore` y `.dockerignore`. Un secreto subido queda en el historial aunque se borre después; el historial está revisado y no tiene ninguno.
- En producción van en el panel de Render; en el CI, en *GitHub → Settings → Secrets*. El CI usa claves de prueba, nunca las reales.
- **La API no arranca** si `SECRET_KEY` falta, tiene menos de 32 caracteres o sigue siendo el texto de ejemplo de `.env.example`. Genera una con `python -c "import secrets; print(secrets.token_urlsafe(32))"`, distinta en cada entorno.
- Si se filtra: se cambia (eso invalida todos los tokens emitidos) y se revisa el historial.

## Vulnerabilidades Conocidas: OWASP API Security Top 10 (2023)
| Riesgo OWASP | Cómo lo mitigamos |
|---|---|
| **API1 · Acceso a objetos de otro usuario** (BOLA) | Cada consulta filtra por el usuario del token. Una entrada o un equipo ajeno responde `404`, igual que si no existiera. Hay tests que lo comprueban en cada endpoint |
| **API2 · Autenticación rota** | bcrypt con límite de 72 bytes, JWT firmados con clave de al menos 32 caracteres, access token corto, refresh token rotatorio, login sin pistas (mensaje y tiempo), rate limiting por IP y bloqueo por cuenta tras 5 fallos |
| **API3 · Exposición de propiedades** (datos de más, *mass assignment*) | Esquemas de salida explícitos (`UserRead` sin el hash). `PATCH` solo acepta los campos editables: `owner_id` o `pokemon_id` no se pueden tocar aunque se envíen |
| **API4 · Consumo de recursos sin límite** | Rate limiting por tipo, paginación de 100 como máximo, equipos de 6 como máximo, imágenes de 2 MB como máximo, timeout de la PokeAPI y caché de búsqueda que no se puede llenar con tipos inventados |
| **API5 · Funciones de otro rol** (BFLA) | No hay funciones de administrador: todos los endpoints trabajan solo con los datos del usuario del token |
| **API6 · Abuso de flujos de negocio** | El registro y el login tienen sus propios límites. Ver *Limitaciones* sobre el registro |
| **API7 · SSRF** | Las imágenes de las fichas solo se descargan de `raw.githubusercontent.com`, por HTTPS y sin seguir redirecciones. Se compara el host exacto |
| **API8 · Mala configuración** | CORS restringido. Cabeceras de seguridad (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy` y, por HTTPS, HSTS). Errores sin trazas internas. Contenedor sin root. Dependencias con versión fija |
| **API9 · Inventario de versiones** | Versiones en la URL (`/api/v1`, `/api/v2`), con cabeceras de deprecación (`Deprecation`, `Sunset` y `Link`) en la v1. Documentadas en el README y en Swagger |
| **API10 · Consumo inseguro de otras APIs** | Las respuestas de la PokeAPI se validan: un formato inesperado da `502`, sin que llegue un `500`. Timeout, y nombres validados antes de llamar fuera |

Además, de la lista OWASP general: **inyección** (SQL parametrizado; `sort` de una lista cerrada; CSV con las fórmulas neutralizadas; logs con los nombres escapados; nombre de fichero limpio en `Content-Disposition`) y **registro y monitorización** (logs de peticiones, auth, 422 y 429, sin contraseñas, tokens ni query strings).

## Resumen de medidas

| Riesgo | Medida | Dónde |
|---|---|---|
| Robo de contraseñas | Hash con `bcrypt` y sal por usuario. Nunca se devuelven ni aparecen en los logs | `app/auth.py`, `app/logs.py` |
| Contraseñas débiles o demasiado largas | Mínimo 8 caracteres, con una mayúscula y un número, y como mucho 72 bytes (más daba `500`) | `UserCreate` en `app/models.py`, `app/auth.py` |
| Suplantación | JWT firmados (HS256 = HMAC-SHA256): el de acceso caduca a los 30 min y el refresh token a los 7 días, con rotación y logout. La API no arranca sin una `SECRET_KEY` de al menos 32 caracteres | `app/auth.py`, `app/config.py` |
| Robo de un refresh token | Duran 7 días y son de un solo uso (rotación). Si se reutiliza uno ya usado, se anulan todos los de la cuenta. El logout lo anula. Un refresh token no sirve para entrar, ni un access token para renovar. Los caducados se borran al arrancar la app y, los de cada usuario, en cada login o renovación | `app/routers/auth.py`, `app/dependencies.py` |
| Cuentas duplicadas o suplantadas con mayúsculas (`Ash`/`ash`, `ASH@x.com`/`ash@x.com`) | El email se guarda en minúsculas y el usuario se compara sin mayúsculas, con un índice único sobre `lower(username)`. El usuario solo admite letras, números y `_ . -` | `app/models.py`, `app/routers/auth.py` |
| Enumeración de usuarios en el login | El mismo error (401, mismo mensaje y mismas cabeceras) para usuario inexistente, contraseña incorrecta y cuenta desactivada, y el mismo tiempo de respuesta (bcrypt siempre, con un hash falso si el usuario no existe). Lo comprueban tests en `tests/test_auth.py` | `app/routers/auth.py` |
| Token de una cuenta borrada o desactivada | Cada petición busca al usuario por el `user_id` del token y comprueba `is_active`. Todos los fallos del token responden el mismo `401` | `app/dependencies.py` |
| Cuentas o entradas duplicadas por peticiones simultáneas | Restricciones `UNIQUE` en la base de datos (usuario, email, Pokémon por usuario). Si salta una, se deshace la transacción y se responde 409 | `app/models.py`, routers `auth`, `pokedex` |
| Acceso a datos ajenos | Cada consulta filtra por el usuario del token. Lo ajeno responde 404, sin confirmar que existe | routers `pokedex`, `teams` |
| Fuerza bruta y abuso | Rate limiting por tipo de endpoint, con la IP real del cliente detrás del proxy de Render (`TRUSTED_PROXY_HOPS`) | `app/limits.py` |
| Fuerza bruta contra una cuenta desde muchas IPs | 5 logins fallidos en 15 min bloquean esa cuenta (`429`), también para usuarios que no existen | `app/limits.py`, `app/routers/auth.py` |
| Inyección SQL | Consultas con SQLModel/SQLAlchemy parametrizadas. El orden (`sort`) sale de una lista cerrada | `app/routers/pokedex.py` |
| Entradas maliciosas | Validación con Pydantic: nombres sin tabuladores ni en blanco, fechas no futuras, identificadores de Pokémon validados antes de llamar a la PokeAPI | `app/models.py`, `app/services/pokeapi_service.py` |
| Uso desde webs ajenas | CORS limitado a `CORS_ORIGINS` y a los métodos y cabeceras que usa la API | `app/main.py` |
| Fallos de un servicio externo | Timeout y traducción de errores de la PokeAPI a 502/504, sin trazas internas | `app/services/pokeapi_service.py` |
| Fuga de secretos | `.env` en `.gitignore` y `.dockerignore`. El CI usa claves de prueba. Historial revisado sin secretos | raíz del repo |
| Robo del token en la red | En producción, la API se sirve solo por HTTPS (Render pone el certificado y redirige HTTP a HTTPS), con HSTS. Sin HTTPS, el token y la contraseña del login viajarían en claro | Render, `app/seguridad.py` |
| Cabeceras del navegador | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` y `Content-Security-Policy: default-src 'none'` en todas las respuestas (la CSP, salvo en `/docs` y `/redoc`, que cargan Swagger de un CDN). Las de `/api/v1/auth` llevan `Cache-Control: no-store`: los tokens no se guardan en ninguna caché | `app/seguridad.py` |
| Dependencias que cambian solas | Versiones exactas (`==`) de **todas** las dependencias, también las indirectas (p. ej. Starlette), generadas desde `uv.lock`: `requirements.txt` (la API, lo que instala Docker) y `requirements-dev.txt` (más tests y linter, lo que instala el CI). Cada build instala lo mismo | `requirements.txt`, `requirements-dev.txt`, `uv.lock` |
| Contenedor comprometido | La imagen corre con un usuario sin privilegios (`api`) | `Dockerfile` |
| Peticiones a otros sitios desde el servidor (SSRF) | Las imágenes de las fichas en PDF solo se descargan de `raw.githubusercontent.com`, por HTTPS y hasta 2 MB. Se compara el host exacto: `raw.githubusercontent.com.evil.com` se rechaza | `app/services/pokeapi_service.py` |
| Datos sensibles en los logs | No se registran contraseñas, tokens, cuerpos de petición ni query strings. En los 422 solo se guarda qué campo falla, nunca el valor enviado | `app/logs.py` |
| Falsear líneas del log (log injection) | Los nombres de usuario se escriben con `%r`, con los saltos de línea escapados. Un `X-Request-ID` del cliente solo se reutiliza si son letras, números y guiones | `app/logs.py`, `app/routers/auth.py` |
| Inyección en la cabecera de descarga | El nombre del fichero de la ficha se limpia antes de ponerlo en `Content-Disposition`. La exportación de la Pokédex usa un nombre fijo (`pokedex.csv` o `pokedex.pdf`) | `app/routers/pokemon.py`, `app/routers/pokedex.py` |
| Fórmulas en el CSV exportado (CSV injection) | Las celdas que empiezan por `=`, `+`, `-`, `@`, tabulador o retorno de carro llevan una comilla delante, para que Excel o LibreOffice no las ejecuten al abrir el fichero | `app/services/export_service.py` |
| Ficheros en el servidor | Los PDF se generan en memoria y se envían sin escribir nada en disco | `app/services/ficha_pdf.py` |

## Limitaciones conocidas
- **El registro revela si un usuario o un email ya existen** (`409`). Basta con registrarse con un usuario inventado y el email de otra persona para saber si tiene cuenta (*enumeración de cuentas*). Lo frena el límite de 5 registros por hora por IP. Taparlo del todo exige verificar el email: responder siempre «te hemos enviado un correo» y avisar por correo si ya tenías cuenta. Eso necesita un servidor de correo y queda fuera de la práctica. Por la misma razón, alguien podría registrarse con un email que no es suyo. El login sí está protegido (mismo mensaje y mismo tiempo).
- **El access token no se puede anular** antes de que caduque (máximo 30 min): el logout anula el refresh token y el cliente debe borrar el access token.
- **El rate limiting es en memoria:** se reinicia al reiniciar la app y no se comparte entre varias instancias (haría falta Redis). Varios usuarios detrás de la misma IP pública (una universidad, una empresa) comparten el límite por IP.
- **`TRUSTED_PROXY_HOPS` tiene que coincidir con la realidad.** En Render hay que ponerlo a `1`; si no, todos los usuarios comparten el límite. Y si se pone sin proxy delante, cualquiera puede elegir su IP con `X-Forwarded-For` y saltarse el límite por IP (el límite por cuenta sigue funcionando).
- **El bloqueo por cuenta lo puede provocar otro:** quien sepa tu nombre de usuario puede fallar 5 veces y dejarte sin entrar 15 minutos. Es el precio de frenar la fuerza bruta; los bloqueos quedan en el log.
- **SQLite** es para desarrollo y la práctica. En producción convendría PostgreSQL.
- **La caché de la búsqueda de Pokémon** (24 h) está en memoria: se pierde al reiniciar y no se comparte entre varias instancias.
