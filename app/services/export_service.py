"""Exportar la Pokédex de un usuario a CSV y a PDF (#11).

Funciones puras: reciben las entradas ya filtradas y ordenadas y devuelven el
fichero. El router decide qué entradas van y cómo se descargan.
"""

import csv
import io
from collections.abc import Sequence
from datetime import UTC, datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.models import PokedexEntry

# Fuentes básicas del PDF: sólo Latin-1. Lo que no cabe (emojis…) sale como «?».
from app.services.ficha_pdf import _texto as _latin1

COLUMNAS = [
    "pokemon_id",
    "pokemon_name",
    "nickname",
    "is_captured",
    "favorite",
    "capture_date",
    "notes",
]

# Una celda que empieza por uno de estos caracteres la interpreta Excel o
# LibreOffice como fórmula. nickname y notes los escribe el usuario, así que
# se neutralizan con una comilla delante (inyección CSV / CSV injection).
INICIO_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M")
    return str(valor)


def _celda_segura(valor) -> str:
    texto = _texto(valor)
    if texto.startswith(INICIO_DE_FORMULA):
        return "'" + texto
    return texto


def pokedex_a_csv(entradas: Sequence[PokedexEntry]) -> str:
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(COLUMNAS)
    for entrada in entradas:
        escritor.writerow(
            [_celda_segura(getattr(entrada, columna)) for columna in COLUMNAS]
        )
    # BOM al principio: sin él, Excel abre el CSV como Latin-1 y rompe las tildes.
    return "﻿" + salida.getvalue()


# ───────────────────────────── PDF ─────────────────────────────


def pokedex_a_pdf(
    entradas: Sequence[PokedexEntry], usuario: str, filtros: dict[str, str]
) -> bytes:
    pdf = FPDF(orientation="landscape")
    pdf.set_title(_latin1(f"Pokédex de {usuario}"))
    pdf.set_author("Pokédex API")
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(
        h=10, text=_latin1(f"Pokédex de {usuario}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )

    pdf.set_font("Helvetica", size=10)
    generado = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    capturados = sum(1 for e in entradas if e.is_captured)
    favoritos = sum(1 for e in entradas if e.favorite)
    lineas = [
        f"Generado: {generado}",
        f"Filtros: {', '.join(f'{k}={v}' for k, v in filtros.items()) or 'ninguno'}",
        f"Total: {len(entradas)} · Capturados: {capturados} · Favoritos: {favoritos}",
    ]
    for linea in lineas:
        pdf.cell(h=6, text=_latin1(linea), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    if not entradas:
        pdf.set_font("Helvetica", "I", 12)
        pdf.cell(text="No hay Pokémon que cumplan los filtros.")
        return bytes(pdf.output())

    pdf.set_font("Helvetica", size=9)
    cabecera = ("#", "Pokémon", "Mote", "Capturado", "Favorito", "Fecha", "Notas")
    with pdf.table(col_widths=(8, 22, 20, 12, 12, 20, 60), text_align="LEFT") as tabla:
        fila = tabla.row()
        for titulo in cabecera:
            fila.cell(_latin1(titulo))
        for e in entradas:
            fila = tabla.row()
            valores = (
                e.pokemon_id,
                e.pokemon_name,
                e.nickname,
                e.is_captured,
                e.favorite,
                e.capture_date,
                e.notes,
            )
            for valor in valores:
                # En el PDF no hay fórmulas: se muestra el texto tal cual.
                fila.cell(_latin1(_texto(valor)))

    return bytes(pdf.output())
