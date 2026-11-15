"""Tests de /pokedex/stats ampliado: tipo más común y racha de capturas (#12)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import select

from app.database import create_db_and_tables
from app.models import PokedexEntry
from app.services.estadisticas import racha_de_capturas, tipo_mas_comun

URL = "/api/v1/pokedex"
HOY = date(2026, 11, 14)


def dia(n: int, hora: int = 12) -> datetime:
    """Momento de hace n días (respecto a HOY), en UTC."""
    d = HOY - timedelta(days=n)
    return datetime(d.year, d.month, d.day, hora, tzinfo=UTC)


def hace(n: int) -> datetime:
    """Momento de hace n días respecto al reloj real (para los tests del endpoint)."""
    return datetime.now(UTC) - timedelta(days=n)


def stats(client, headers) -> dict:
    r = client.get(f"{URL}/stats", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- Tipo más común (función) ---------------------------------------------------


def test_tipo_mas_comun_cuenta_cada_tipo():
    assert tipo_mas_comun([["fire"], ["water"], ["fire", "flying"]]) == "fire"


def test_un_pokemon_de_dos_tipos_cuenta_para_los_dos():
    # grass aparece 2 veces (una en el doble tipo) y gana a poison (1).
    assert tipo_mas_comun([["grass", "poison"], ["grass"]]) == "grass"


def test_empate_gana_el_primero_por_orden_alfabetico():
    assert tipo_mas_comun([["water"], ["fire"]]) == "fire"
    assert tipo_mas_comun([["fire"], ["water"]]) == "fire"  # mismo resultado


@pytest.mark.parametrize("entrada", [[], [[]], [[], None]])
def test_sin_tipos_devuelve_none(entrada):
    assert tipo_mas_comun(entrada) is None


# --- Racha de capturas (función) ---------------------------------------------------


def test_sin_capturas_no_hay_racha():
    assert racha_de_capturas([], HOY) == 0
    assert racha_de_capturas([None, None], HOY) == 0


def test_racha_que_llega_a_hoy():
    assert racha_de_capturas([dia(0), dia(1), dia(2)], HOY) == 3


def test_si_hoy_aun_no_has_capturado_la_racha_sigue_desde_ayer():
    assert racha_de_capturas([dia(1), dia(2)], HOY) == 2


def test_un_dia_sin_capturas_rompe_la_racha():
    # Hoy, ayer y hace 3 días: el hueco de hace 2 días corta la racha en 2.
    assert racha_de_capturas([dia(0), dia(1), dia(3), dia(4)], HOY) == 2


def test_la_racha_caduca_si_la_ultima_captura_fue_antes_de_ayer():
    assert racha_de_capturas([dia(2), dia(3), dia(4)], HOY) == 0


def test_varias_capturas_el_mismo_dia_cuentan_una_vez():
    assert racha_de_capturas([dia(0, 9), dia(0, 18), dia(1, 10)], HOY) == 2


def test_el_orden_de_las_fechas_no_importa():
    assert racha_de_capturas([dia(2), dia(0), dia(1)], HOY) == 3


def test_fechas_sin_zona_horaria_se_toman_como_utc():
    # Así las devuelve SQLite.
    sin_zona = [dia(0).replace(tzinfo=None), dia(1).replace(tzinfo=None)]
    assert racha_de_capturas(sin_zona, HOY) == 2


def test_cuenta_el_dia_en_utc():
    # Las 00:30 del día 14 en Madrid (UTC+1) son las 23:30 del 13 en UTC.
    from datetime import timezone

    madrid = timezone(timedelta(hours=1))
    madrugada = datetime(2026, 11, 14, 0, 30, tzinfo=madrid)
    assert racha_de_capturas([madrugada], HOY) == 1  # cuenta como ayer (día 13)
    assert racha_de_capturas([madrugada], date(2026, 11, 16)) == 0


def test_racha_larga_que_cruza_de_mes():
    fechas = [dia(n) for n in range(20)]  # del 26 de octubre al 14 de noviembre
    assert racha_de_capturas(fechas, HOY) == 20


# --- Endpoint ------------------------------------------------------------------------


def test_stats_completas(client, auth_headers, test_user, add_to_pokedex):
    # bulbasaur (grass, poison), charmander (fire), eevee y snorlax (normal)
    add_to_pokedex(test_user, 1, 4)
    add_to_pokedex(test_user, 133, is_captured=True, capture_date=hace(0))
    add_to_pokedex(test_user, 143, is_captured=True, capture_date=hace(1))
    assert stats(client, auth_headers) == {
        "total_pokemon": 4,
        "captured": 2,
        "favorites": 0,
        "completion_percentage": 50.0,
        "national_dex_percentage": 0.2,  # 2 de 1025
        "most_common_type": "normal",
        "most_common_types": ["normal"],
        "capture_streak_days": 2,
    }


def test_tipo_mas_comun_cuenta_toda_la_pokedex(
    client, auth_headers, test_user, add_to_pokedex
):
    # Capturados o no, todos cuentan: es el tipo más común de tu Pokédex.
    add_to_pokedex(test_user, 4)  # fire, sin capturar
    add_to_pokedex(test_user, 7, 25)  # water, electric
    add_to_pokedex(test_user, 150, pokemon_types=["fire"])
    assert stats(client, auth_headers)["most_common_type"] == "fire"


def test_solo_cuentan_mis_pokemon(
    client, auth_headers, test_user, other_user, add_to_pokedex
):
    add_to_pokedex(test_user, 25, is_captured=True, capture_date=hace(0))
    add_to_pokedex(other_user, 4, 133, 143, is_captured=True, capture_date=hace(1))
    datos = stats(client, auth_headers)
    assert datos["most_common_type"] == "electric"
    assert datos["capture_streak_days"] == 1


def test_la_racha_ignora_los_que_ya_no_estan_capturados(
    client, auth_headers, test_user, add_to_pokedex
):
    # Si lo sueltas (is_captured=False), su fecha ya no cuenta.
    add_to_pokedex(test_user, 25, is_captured=False, capture_date=hace(0))
    assert stats(client, auth_headers)["capture_streak_days"] == 0


def test_capturar_desde_la_api_empieza_la_racha(client, auth_headers):
    r = client.post(
        URL, json={"pokemon_id": 25, "is_captured": True}, headers=auth_headers
    )
    assert r.status_code == 201
    datos = stats(client, auth_headers)
    assert datos["capture_streak_days"] == 1
    assert datos["most_common_type"] == "electric"


def test_stats_exige_token(client):
    assert client.get(f"{URL}/stats").status_code == 401


# --- Los tipos se guardan al añadir ------------------------------------------------


def test_al_anadir_se_guardan_los_tipos(client, auth_headers, session):
    r = client.post(URL, json={"pokemon_id": 1}, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["pokemon_types"] == ["grass", "poison"]
    entrada = session.exec(select(PokedexEntry)).one()
    assert entrada.pokemon_types == ["grass", "poison"]


def test_los_tipos_salen_en_el_listado(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 4)
    [entrada] = client.get(URL, headers=auth_headers).json()
    assert entrada["pokemon_types"] == ["fire"]


# --- Base de datos creada antes de este cambio ---------------------------------------


def _motor_en_memoria():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


def test_anade_la_columna_a_una_base_de_datos_antigua():
    motor = _motor_en_memoria()
    with motor.begin() as c:
        # La tabla tal como era antes de la #12: sin pokemon_types.
        c.execute(
            text(
                "CREATE TABLE pokedexentry (id INTEGER PRIMARY KEY, owner_id INTEGER, "
                "pokemon_id INTEGER, pokemon_name VARCHAR, pokemon_sprite VARCHAR, "
                "nickname VARCHAR, notes VARCHAR, is_captured BOOLEAN, "
                "favorite BOOLEAN, capture_date DATETIME, created_at DATETIME)"
            )
        )
        c.execute(
            text(
                "INSERT INTO pokedexentry (id, owner_id, pokemon_id, pokemon_name, "
                "is_captured, favorite) VALUES (1, 1, 25, 'pikachu', 1, 0)"
            )
        )

    create_db_and_tables(motor)

    columnas = {c["name"] for c in inspect(motor).get_columns("pokedexentry")}
    assert "pokemon_types" in columnas
    with motor.connect() as c:
        # La fila que ya existía conserva sus datos y recibe una lista vacía.
        fila = c.execute(text("SELECT pokemon_name, pokemon_types FROM pokedexentry"))
        assert fila.one() == ("pikachu", "[]")


def test_crear_las_tablas_dos_veces_no_falla():
    motor = _motor_en_memoria()
    create_db_and_tables(motor)
    create_db_and_tables(motor)  # la columna ya existe: no se vuelve a añadir
    columnas = [c["name"] for c in inspect(motor).get_columns("pokedexentry")]
    assert columnas.count("pokemon_types") == 1
