"""Ficha de un Pokémon en PDF (tamaño A5), con fpdf2.

Recibe el diccionario que devuelve PokeAPIService.get_pokemon() y, si la hay, la
imagen ya descargada. No llama a internet: así se puede probar sin red.
"""

import io
import logging

from fpdf import FPDF
from fpdf.errors import FPDFException

logger = logging.getLogger("pokedex_api.ficha")

# Colores de cada tipo (RGB), los habituales en los juegos.
COLORES_TIPO = {
    "normal": (168, 167, 122),
    "fire": (238, 129, 48),
    "water": (99, 144, 240),
    "electric": (247, 208, 44),
    "grass": (122, 199, 76),
    "ice": (150, 217, 214),
    "fighting": (194, 46, 40),
    "poison": (163, 62, 161),
    "ground": (226, 191, 101),
    "flying": (169, 143, 243),
    "psychic": (249, 85, 135),
    "bug": (166, 185, 26),
    "rock": (182, 161, 54),
    "ghost": (115, 87, 151),
    "dragon": (111, 53, 252),
    "dark": (112, 87, 70),
    "steel": (183, 183, 206),
    "fairy": (214, 133, 173),
}
COLOR_POR_DEFECTO = (120, 120, 120)

NOMBRES_STATS = {
    "hp": "PS",
    "attack": "Ataque",
    "defense": "Defensa",
    "special_attack": "At. especial",
    "special_defense": "Def. especial",
    "speed": "Velocidad",
}
# Ninguna estadística base llega a 255: es el máximo posible en los juegos.
MAX_STAT = 255

ANCHO, ALTO = 148, 210  # A5 en mm
MARGEN = 12


def _texto(valor) -> str:
    """Las fuentes estándar de PDF solo tienen latin-1: lo demás se cambia por '?'."""
    return str(valor).encode("latin-1", "replace").decode("latin-1")


def _bonito(nombre: str) -> str:
    """'mr-mime' → 'Mr Mime'."""
    return nombre.replace("-", " ").title()


def _claro(color: tuple[int, int, int]) -> bool:
    r, g, b = color
    return (0.299 * r + 0.587 * g + 0.114 * b) > 160


def generar_ficha(pokemon: dict, imagen: bytes | None = None) -> bytes:
    tipos = pokemon.get("types") or []
    color = (
        COLORES_TIPO.get(tipos[0], COLOR_POR_DEFECTO) if tipos else COLOR_POR_DEFECTO
    )

    pdf = FPDF(format=(ANCHO, ALTO))
    pdf.set_auto_page_break(False)
    pdf.set_title(_texto(f"Ficha de {_bonito(pokemon['name'])}"))
    pdf.set_creator("Pokédex API")
    pdf.add_page()

    # ── Cabecera con el color del primer tipo ──
    pdf.set_fill_color(*color)
    pdf.rect(0, 0, ANCHO, 34, style="F")
    tinta = (30, 30, 30) if _claro(color) else (255, 255, 255)
    pdf.set_text_color(*tinta)
    pdf.set_xy(MARGEN, 9)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, f"#{pokemon['id']:04d}")
    pdf.set_xy(MARGEN, 15)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 11, _texto(_bonito(pokemon["name"])))

    # ── Tipos como etiquetas ──
    x = MARGEN
    pdf.set_font("Helvetica", "B", 9)
    for tipo in tipos:
        c = COLORES_TIPO.get(tipo, COLOR_POR_DEFECTO)
        texto = _texto(tipo.upper())
        ancho = pdf.get_string_width(texto) + 8
        pdf.set_fill_color(*c)
        pdf.set_draw_color(255, 255, 255)
        pdf.set_line_width(0.6)
        pdf.rect(x, 38, ancho, 7, style="DF", round_corners=True, corner_radius=2)
        pdf.set_text_color(*((30, 30, 30) if _claro(c) else (255, 255, 255)))
        pdf.set_xy(x, 38)
        pdf.cell(ancho, 7, texto, align="C")
        x += ancho + 3

    # ── Imagen ──
    y = 50
    if imagen:
        try:
            pdf.image(
                io.BytesIO(imagen),
                x=(ANCHO - 62) / 2,
                y=y,
                w=62,
                h=62,
                keep_aspect_ratio=True,
            )
        # Imagen corrupta o de un formato raro: la ficha sale igual, sin ella.
        except (OSError, ValueError, FPDFException) as error:
            logger.warning("imagen no válida para %s: %s", pokemon["name"], error)
            imagen = None
    if not imagen:
        pdf.set_draw_color(200, 200, 200)
        pdf.set_line_width(0.3)
        pdf.rect((ANCHO - 62) / 2, y, 62, 62, style="D")
        pdf.set_text_color(150, 150, 150)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_xy((ANCHO - 62) / 2, y + 28)
        pdf.cell(62, 6, "Sin imagen", align="C")
    y += 68

    # ── Datos ──
    pdf.set_text_color(30, 30, 30)
    altura = pokemon.get("height_m")
    peso = pokemon.get("weight_kg")
    filas = [
        ("Altura", f"{altura:.1f} m" if altura is not None else "-"),
        ("Peso", f"{peso:.1f} kg" if peso is not None else "-"),
        (
            "Habilidades",
            ", ".join(
                _bonito(a["name"]) + (" (oculta)" if a.get("is_hidden") else "")
                for a in pokemon.get("abilities") or []
            )
            or "-",
        ),
    ]
    for etiqueta, valor in filas:
        pdf.set_xy(MARGEN, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(26, 6, _texto(etiqueta))
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(ANCHO - 2 * MARGEN - 26, 6, _texto(valor))
        y = pdf.get_y() + 0.5

    # ── Estadísticas base con barras ──
    y += 3
    pdf.set_xy(MARGEN, y)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _texto("Estadísticas base"))
    y += 9
    stats = pokemon.get("stats") or {}
    ancho_barra = ANCHO - 2 * MARGEN - 26 - 12
    total = 0
    for clave, nombre in NOMBRES_STATS.items():
        valor = stats.get(clave)
        pdf.set_xy(MARGEN, y)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(26, 5, _texto(nombre))
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(10, 5, "-" if valor is None else str(valor), align="R")
        x_barra = MARGEN + 38
        pdf.set_fill_color(232, 232, 232)
        pdf.rect(x_barra, y + 1.2, ancho_barra, 2.8, style="F")
        if valor:
            total += valor
            pdf.set_fill_color(*color)
            pdf.rect(
                x_barra,
                y + 1.2,
                ancho_barra * min(valor, MAX_STAT) / MAX_STAT,
                2.8,
                style="F",
            )
        y += 6
    pdf.set_xy(MARGEN, y)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(26, 5, "Total")
    pdf.cell(10, 5, str(total), align="R")

    # ── Pie ──
    pdf.set_xy(MARGEN, ALTO - 12)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(0, 5, _texto("Datos de PokeAPI (pokeapi.co) · Pokédex API"), align="C")

    return bytes(pdf.output())
