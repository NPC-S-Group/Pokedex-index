# `.github/workflows/` · integración continua

`ci.yml` se ejecuta en cada push y en cada PR hacia `main` y `develop`.

| Trabajo | Dónde | Qué hace |
|---|---|---|
| `tests` | `ubuntu-latest` (GitHub) | Instala `requirements.txt` y ejecuta `pytest` con cobertura. **Falla si algún test falla o si la cobertura baja del 80 %** |
| `docker` | Runner propio del homelab | Construye la imagen y comprueba que la API arranca (`/health`, `/docs`). Solo corre si la variable del repo `HOMELAB_RUNNER` vale `true`; si no, se salta |

- Las variables `SECRET_KEY` y `DATABASE_URL` del CI son de prueba, nunca las reales.
- Un PR con el CI en rojo no se integra.

**Estado (10 nov):** `develop` está en rojo por cobertura (63 %) desde que entraron los archivos iniciales sin tests. Se pone en verde al integrar #22, #23 y #24, que llegan al 81 %.
