"""Cálculos de /pokedex/stats que no son un simple COUNT (#12).

Funciones puras: reciben datos ya leídos de la base de datos y la fecha de hoy.
Así se prueban con cualquier fecha sin depender del reloj.
"""

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta


def tipo_mas_comun(tipos_por_pokemon: Iterable[list[str]]) -> str | None:
    """El tipo que más se repite. Un Pokémon de dos tipos cuenta para los dos.

    Empate: gana el primero en orden alfabético, para que el resultado no cambie
    según el orden en que se lean las filas. Sin tipos: None.
    """
    cuenta = Counter(t for tipos in tipos_por_pokemon for t in tipos or [])
    if not cuenta:
        return None
    return min(cuenta, key=lambda tipo: (-cuenta[tipo], tipo))


def _dia(momento: datetime) -> date:
    # SQLite devuelve las fechas sin zona horaria; las guardamos siempre en UTC.
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC).date()


def racha_de_capturas(fechas: Iterable[datetime | None], hoy: date) -> int:
    """Días seguidos con al menos una captura, contando hacia atrás desde hoy.

    Si hoy todavía no has capturado nada, la racha sigue viva desde ayer (como
    en cualquier app con rachas): solo se rompe cuando pasa un día entero sin
    capturas. Varias capturas el mismo día cuentan como un solo día.
    """
    dias = {_dia(f) for f in fechas if f is not None}
    if hoy in dias:
        dia = hoy
    elif hoy - timedelta(days=1) in dias:
        dia = hoy - timedelta(days=1)
    else:
        return 0
    racha = 0
    while dia in dias:
        racha += 1
        dia -= timedelta(days=1)
    return racha
