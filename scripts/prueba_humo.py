"""Prueba de humo (smoke test) de la API desplegada.

PARA QUÉ SIRVE
    Recorre la API ya publicada como lo haría un usuario real y comprueba que todo
    responde bien: registro y login, PokeAPI real, Pokédex, estadísticas, exportar,
    API v2, equipos, aislamiento entre usuarios y CORS. Al final borra lo que ha creado.

    No sustituye a los tests de pytest: esos prueban el CÓDIGO con una base de datos en
    memoria y una PokeAPI falsa. Esta prueba comprueba el DESPLIEGUE: la URL pública,
    las variables configuradas en Render, la base de datos real y la PokeAPI de verdad.
    Detecta lo que pytest no puede ver, como una variable que falta en Render, un
    puerto mal configurado o una versión que no ha llegado a desplegarse.

CUÁNDO SE USA
    - Automáticamente: el trabajo deploy-render del CI la lanza después de cada
      despliegue en Render, cuando /health ya devuelve el commit recién fusionado.
    - A mano: antes de la entrega, de la defensa o del vídeo, o si algo parece roto.
        python scripts/prueba_humo.py                      # contra Render
        python scripts/prueba_humo.py http://localhost:8000  # contra la API en local

    La usamos por primera vez el 14-11-2026, justo después del primer despliegue en
    Render: dio 48 de 49 comprobaciones correctas. La que falló demostró su utilidad:
    las cabeceras de deprecación de la v1 todavía no estaban en main, y por tanto
    tampoco en Render, aunque pytest pasaba entero en develop.

QUÉ DEJA EN LA API
    Dos usuarios con nombre aleatorio (prueba<hex>a y prueba<hex>b), porque la API no
    permite borrar usuarios. Sus Pokémon y equipos sí se borran. En Render la base de
    datos se vacía en cada despliegue, así que no se acumulan. Usa 3 de los 5 registros
    por hora que permite el límite de una misma IP.

Sale con código 0 si todo va bien y con 1 si falla alguna comprobación.
"""

import csv
import io
import os
import secrets
import sys
import time

import httpx

URL_POR_DEFECTO = "https://pokedex-api-wrok.onrender.com"

resultados: list[tuple[str, bool]] = []


def check(nombre: str, cond, detalle="") -> None:
    resultados.append((nombre, bool(cond)))
    print(("OK   " if cond else "FALLO"), nombre, "" if cond else f"-> {detalle}")


def main(base: str) -> int:
    c = httpx.Client(base_url=base, timeout=120)
    print(f"Prueba de humo contra {base}\n")

    # --- Sistema -----------------------------------------------------------------
    inicio = time.time()
    r = c.get("/health")
    check("health", r.status_code == 200 and r.json().get("status") == "ok", r.text)
    print(
        f"     (primera respuesta en {time.time() - inicio:.1f} s; en Render, si dormía, ~50 s)"
    )
    check("docs (Swagger)", c.get("/docs").status_code == 200)
    rutas = c.get("/openapi.json").json()["paths"]
    check("openapi tiene v1 y v2", {"/api/v1/pokedex", "/api/v2/pokedex"} <= set(rutas))

    sufijo = secrets.token_hex(3)
    a, b = f"prueba{sufijo}a", f"prueba{sufijo}b"
    clave = "Prueba" + secrets.token_hex(4) + "1"

    # --- Autenticación -------------------------------------------------------------
    def registrar(usuario, email):
        datos = {"username": usuario, "email": email, "password": clave}
        return c.post("/api/v1/auth/register", json=datos)

    r = registrar(a, f"{a}@ejemplo.com")
    check("registro A -> 201", r.status_code == 201, r.text)
    check("registro no devuelve la contraseña", "password" not in r.text, r.text)
    r = registrar(a, f"otro{a}@ejemplo.com")
    check("registro duplicado -> 409", r.status_code == 409, r.text)
    check("registro B -> 201", registrar(b, f"{b}@ejemplo.com").status_code == 201)

    r = c.post("/api/v1/auth/login", data={"username": a, "password": "Incorrecta1"})
    check("login con contraseña mala -> 401", r.status_code == 401, r.text)
    r = c.post("/api/v1/auth/login", data={"username": a, "password": clave})
    check("login A -> 200 con token", r.json().get("token_type") == "bearer", r.text)
    ha = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = c.post("/api/v1/auth/login", data={"username": b, "password": clave})
    hb = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = c.get("/api/v1/auth/me", headers=ha)
    check("/auth/me devuelve A", r.json().get("username") == a, r.text)
    check("sin token -> 401", c.get("/api/v1/pokedex").status_code == 401)
    falso = {"Authorization": "Bearer abc.def.ghi"}
    check(
        "token inventado -> 401",
        c.get("/api/v1/auth/me", headers=falso).status_code == 401,
    )

    # --- PokeAPI real ----------------------------------------------------------------
    r = c.get("/api/v1/pokemon/pikachu", headers=ha)
    check(
        "detalle de pikachu",
        r.status_code == 200 and r.json()["id"] == 25,
        r.text[:200],
    )
    r = c.get("/api/v1/pokemon/search", params={"q": "saur"}, headers=ha)
    check("búsqueda 'saur'", r.json().get("count", 0) > 0, r.text[:200])
    r = c.get("/api/v1/pokemon/charizard/card", headers=ha)
    check("ficha PDF de charizard", r.content[:4] == b"%PDF", r.status_code)
    r = c.get("/api/v1/pokemon/noexiste", headers=ha)
    check("pokémon inexistente -> 404", r.status_code == 404)

    # --- Pokédex -------------------------------------------------------------------
    def anadir(**datos):
        return c.post("/api/v1/pokedex", json=datos, headers=ha)

    r = anadir(pokemon_id=25, nickname="Pika", is_captured=True)
    check("añadir pikachu capturado -> 201", r.json().get("capture_date"), r.text)
    pika = r.json()
    r = anadir(pokemon_id=1, favorite=True)
    check(
        "añadir bulbasaur -> 201", r.json().get("pokemon_name") == "bulbasaur", r.text
    )
    bulba = r.json()
    r = anadir(pokemon_id=6, notes='=HYPERLINK("x")')
    check("añadir charizard -> 201", r.status_code == 201, r.text)
    chari = r.json()
    check("duplicado -> 409", anadir(pokemon_id=25).status_code == 409)
    check("id fuera de rango -> 422", anadir(pokemon_id=5000).status_code == 422)

    r = c.get("/api/v1/pokedex", headers=ha)
    check("listado v1 con 3 entradas", len(r.json()) == 3, r.text[:200])
    # Solo si la versión desplegada ya marca la v1 como obsoleta (mejora de #14).
    if rutas["/api/v1/pokedex"]["get"].get("deprecated"):
        cabeceras = ("deprecation", "sunset", "link")
        check("v1 avisa de la deprecación", all(h in r.headers for h in cabeceras))
    r = c.get("/api/v1/pokedex", params={"captured": True}, headers=ha)
    check("filtro captured=true", [e["pokemon_id"] for e in r.json()] == [25], r.text)
    r = c.get("/api/v1/pokedex", params={"sort": "pokemon_name"}, headers=ha)
    nombres = [e["pokemon_name"] for e in r.json()]
    check("orden por nombre", nombres == ["bulbasaur", "charizard", "pikachu"], nombres)
    r = c.get("/api/v1/pokedex", params={"sort": "owner_id"}, headers=ha)
    check("sort no permitido -> 422", r.status_code == 422)

    url_bulba = f"/api/v1/pokedex/{bulba['id']}"
    r = c.patch(url_bulba, json={"is_captured": True, "nickname": "Bulby"}, headers=ha)
    check("PATCH capturar pone fecha", r.json().get("capture_date"), r.text)
    r = c.patch(url_bulba, json={"capture_date": "2026-01-15T10:00:00"}, headers=ha)
    check("PATCH con fecha sin zona -> 200", r.status_code == 200, r.text)

    r = c.get("/api/v1/pokedex/stats", headers=ha)
    stats = r.json()
    check(
        "estadísticas",
        stats.get("total_pokemon") == 3 and stats["captured"] == 2,
        r.text,
    )

    r = c.get("/api/v1/pokedex/export", params={"format": "csv"}, headers=ha)
    filas = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    check("exportar CSV (3 filas)", len(filas) == 3, r.text[:200])
    check("el CSV neutraliza fórmulas", any(f["notes"].startswith("'=") for f in filas))
    r = c.get("/api/v1/pokedex/export", params={"format": "pdf"}, headers=ha)
    check("exportar PDF", r.content[:4] == b"%PDF", r.status_code)

    # --- API v2 --------------------------------------------------------------------
    r = c.get("/api/v2/pokedex", params={"limit": 2}, headers=ha)
    pagina = r.json()
    check(
        "v2: sobre con total y has_more",
        pagina.get("total") == 3 and pagina["has_more"] and len(pagina["items"]) == 2,
        r.text[:200],
    )
    check(
        "v2: pokémon agrupado",
        set(pagina["items"][0]["pokemon"]) == {"id", "name", "sprite"},
    )
    check("v2 no está obsoleta", "deprecation" not in r.headers)

    # --- Equipos -------------------------------------------------------------------
    def equipo(ids):
        return c.post(
            "/api/v1/teams", json={"name": "Prueba", "pokemon_ids": ids}, headers=ha
        )

    r = equipo([25, 1, 6])
    check("crear equipo -> 201", len(r.json().get("members", [])) == 3, r.text)
    team = r.json()
    check(
        "equipo con un pokémon que no tengo -> error",
        equipo([150]).status_code in (400, 404, 422),
    )
    check("equipo de 7 -> 422", equipo([1, 2, 3, 4, 5, 6, 7]).status_code == 422)
    r = c.get(f"/api/v1/teams/{team['id']}/export", headers=ha)
    check("equipo en PDF", r.content[:4] == b"%PDF", r.status_code)

    # --- Aislamiento entre usuarios ----------------------------------------------
    check(
        "B no ve la entrada de A -> 404",
        c.get(f"/api/v1/pokedex/{pika['id']}", headers=hb).status_code == 404,
    )
    check(
        "B no ve el equipo de A -> 404",
        c.get(f"/api/v1/teams/{team['id']}", headers=hb).status_code == 404,
    )
    check(
        "B no puede borrar lo de A -> 404",
        c.delete(f"/api/v1/pokedex/{pika['id']}", headers=hb).status_code == 404,
    )
    check(
        "la Pokédex de B está vacía",
        c.get("/api/v2/pokedex", headers=hb).json()["total"] == 0,
    )

    # --- Borrar --------------------------------------------------------------------
    check(
        "borrar charizard -> 204",
        c.delete(f"/api/v1/pokedex/{chari['id']}", headers=ha).status_code == 204,
    )
    r = c.get(f"/api/v1/teams/{team['id']}", headers=ha)
    miembros = [m["pokemon_id"] for m in r.json()["members"]]
    check("charizard sale del equipo", miembros == [25, 1], miembros)

    # --- CORS y trazabilidad ---------------------------------------------------------
    r = c.get("/health", headers={"Origin": "http://localhost:5173"})
    check(
        "CORS permite localhost:5173",
        r.headers.get("access-control-allow-origin") == "http://localhost:5173",
    )
    r = c.get("/api/v1/pokedex", headers={**ha, "Origin": "https://malicioso.example"})
    check(
        "CORS no permite otros orígenes", "access-control-allow-origin" not in r.headers
    )
    check("X-Request-ID en la respuesta", "x-request-id" in r.headers)

    # --- Limpieza ------------------------------------------------------------------
    c.delete(f"/api/v1/teams/{team['id']}", headers=ha)
    for entrada in (pika, bulba):
        c.delete(f"/api/v1/pokedex/{entrada['id']}", headers=ha)
    check(
        "limpieza: la Pokédex de A queda vacía",
        c.get("/api/v2/pokedex", headers=ha).json()["total"] == 0,
    )

    correctas = sum(1 for _, ok in resultados if ok)
    print(f"\n{correctas}/{len(resultados)} comprobaciones correctas")
    return 0 if correctas == len(resultados) else 1


def ejecutar(base: str) -> int:
    try:
        return main(base)
    # Una respuesta inesperada (otro JSON, un error de red…) no debe dejarla a medias.
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
        print(f"\nFALLO inesperado: {type(error).__name__}: {error}")
        correctas = sum(1 for _, ok in resultados if ok)
        print(f"{correctas}/{len(resultados)} comprobaciones correctas antes del fallo")
        return 1


if __name__ == "__main__":
    base = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("PRUEBA_HUMO_URL", URL_POR_DEFECTO)
    )
    sys.exit(ejecutar(base.rstrip("/")))
