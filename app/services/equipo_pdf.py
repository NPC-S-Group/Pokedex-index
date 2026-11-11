"""Equipo en PDF: portada con estadísticas combinadas y una ficha por Pokémon.

Reutiliza la ficha de app/services/ficha_pdf.py (misma librería y mismo estilo).
No llama a internet: recibe los datos y las imágenes ya descargados.
"""

from collections import Counter

from fpdf import FPDF

from app.services.ficha_pdf import (
    ALTO,
    ANCHO,
    COLOR_POR_DEFECTO,
    COLORES_TIPO,
    MARGEN,
    MAX_STAT,
    NOMBRES_STATS,
    _bonito,
    _texto,
    dibujar_ficha,
)

COLOR_EQUIPO = (204, 0, 0)  # rojo Pokédex


def estadisticas_combinadas(pokemons: list[dict]) -> dict:
    """Suma y media de cada estadística base, total del equipo y tipos que cubre.

    Si a un Pokémon le falta una estadística, no cuenta para esa media.
    """
    total, media = {}, {}
    for clave in NOMBRES_STATS:
        valores = [
            p["stats"][clave] for p in pokemons if (p.get("stats") or {}).get(clave)
        ]
        total[clave] = sum(valores)
        media[clave] = round(sum(valores) / len(valores), 1) if valores else 0.0
    tipos = Counter(t for p in pokemons for t in p.get("types") or [])
    return {
        "total": total,
        "media": media,
        "total_equipo": sum(total.values()),
        "tipos": dict(tipos.most_common()),
    }


def generar_pdf_equipo(
    nombre: str, descripcion: str | None, miembros: list[dict]
) -> bytes:
    """miembros: [{"position", "nickname", "pokemon": dict, "imagen": bytes|None}]"""
    pdf = FPDF(format=(ANCHO, ALTO))
    pdf.set_auto_page_break(False)
    pdf.set_title(_texto(f"Equipo {nombre}"))
    pdf.set_creator("Pokédex API")

    pokemons = [m["pokemon"] for m in miembros]
    stats = estadisticas_combinadas(pokemons)
    _portada(pdf, nombre, descripcion, miembros, stats)
    for m in miembros:
        dibujar_ficha(pdf, m["pokemon"], m.get("imagen"))
    return bytes(pdf.output())


def _portada(pdf: FPDF, nombre, descripcion, miembros, stats) -> None:
    pdf.add_page()

    # ── Cabecera ──
    pdf.set_fill_color(*COLOR_EQUIPO)
    pdf.rect(0, 0, ANCHO, 30, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(MARGEN, 7)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, "EQUIPO DE BATALLA")
    pdf.set_xy(MARGEN, 13)
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(ANCHO - 2 * MARGEN, 11, _texto(nombre))

    y = 34
    pdf.set_text_color(60, 60, 60)
    if descripcion:
        pdf.set_xy(MARGEN, y)
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(ANCHO - 2 * MARGEN, 5, _texto(descripcion))
        y = pdf.get_y() + 2

    # ── Miembros ──
    y = _titulo(pdf, "Miembros", y)
    for m in miembros:
        p = m["pokemon"]
        pdf.set_xy(MARGEN, y)
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(7, 5.5, str(m["position"]))
        texto = _bonito(p["name"])
        if m.get("nickname"):
            texto += f' "{m["nickname"]}"'
        pdf.cell(58, 5.5, _texto(texto))
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(0, 5.5, _texto(" / ".join(p.get("types") or [])))
        y += 5.5

    # ── Estadísticas combinadas ──
    y = _titulo(pdf, "Estadísticas combinadas", y + 3)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(120, 120, 120)
    pdf.set_xy(MARGEN + 26, y)
    pdf.cell(12, 4, "Suma", align="R")
    pdf.cell(12, 4, "Media", align="R")
    y += 5
    ancho_barra = ANCHO - 2 * MARGEN - 26 - 24 - 4
    for clave, etiqueta in NOMBRES_STATS.items():
        media = stats["media"][clave]
        pdf.set_xy(MARGEN, y)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(26, 5, _texto(etiqueta))
        pdf.set_text_color(30, 30, 30)
        pdf.cell(12, 5, str(stats["total"][clave]), align="R")
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(12, 5, f"{media:g}", align="R")
        x_barra = MARGEN + 26 + 24 + 4
        pdf.set_fill_color(232, 232, 232)
        pdf.rect(x_barra, y + 1.2, ancho_barra, 2.8, style="F")
        if media:
            pdf.set_fill_color(*COLOR_EQUIPO)
            pdf.rect(
                x_barra, y + 1.2, ancho_barra * min(media, MAX_STAT) / MAX_STAT, 2.8,
                style="F",
            )
        y += 6
    pdf.set_xy(MARGEN, y)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(26, 5, "Total equipo")
    pdf.cell(12, 5, str(stats["total_equipo"]), align="R")
    y += 8

    # ── Tipos ──
    y = _titulo(pdf, "Tipos del equipo", y)
    x = MARGEN
    pdf.set_font("Helvetica", "B", 8)
    for tipo, veces in stats["tipos"].items():
        texto = _texto(f"{tipo.upper()} x{veces}")
        ancho = pdf.get_string_width(texto) + 6
        if x + ancho > ANCHO - MARGEN:
            x, y = MARGEN, y + 8
        pdf.set_fill_color(*COLORES_TIPO.get(tipo, COLOR_POR_DEFECTO))
        pdf.rect(x, y, ancho, 6, style="F", round_corners=True, corner_radius=2)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(x, y)
        pdf.cell(ancho, 6, texto, align="C")
        x += ancho + 2

    # ── Pie ──
    pdf.set_xy(MARGEN, ALTO - 12)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(0, 5, _texto("Datos de PokeAPI (pokeapi.co) · Pokédex API"), align="C")


def _titulo(pdf: FPDF, texto: str, y: float) -> float:
    pdf.set_xy(MARGEN, y)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 7, _texto(texto))
    return y + 8
