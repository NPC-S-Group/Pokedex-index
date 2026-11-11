"""Tests de exportar la Pokédex a CSV y PDF (#11)."""

import csv
import io
from datetime import UTC, datetime

from pypdf import PdfReader

from app.services.export_service import COLUMNAS, pokedex_a_csv, pokedex_a_pdf

URL = "/api/v1/pokedex/export"


def _filas_csv(respuesta) -> list[dict]:
    texto = respuesta.content.decode("utf-8-sig")  # -sig quita el BOM
    return list(csv.DictReader(io.StringIO(texto)))


def _texto_pdf(contenido: bytes) -> str:
    lector = PdfReader(io.BytesIO(contenido))
    return "\n".join(pagina.extract_text() for pagina in lector.pages)


# ───────────────────────────── CSV ─────────────────────────────


def test_csv_por_defecto(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, 1)
    r = client.get(URL, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="pokedex.csv"'
    filas = _filas_csv(r)
    assert list(filas[0].keys()) == COLUMNAS
    assert [f["pokemon_name"] for f in filas] == ["bulbasaur", "pikachu"]


def test_csv_lleva_bom_para_excel(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25)
    r = client.get(URL, params={"format": "csv"}, headers=auth_headers)
    assert r.content.startswith("﻿".encode())


def test_csv_campos(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(
        test_user,
        25,
        nickname="Pika",
        notes="Mi primer Pokémon, ¡qué ilusión!",
        is_captured=True,
        favorite=True,
        capture_date=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
    )
    (fila,) = _filas_csv(client.get(URL, headers=auth_headers))
    assert fila == {
        "pokemon_id": "25",
        "pokemon_name": "pikachu",
        "nickname": "Pika",
        "is_captured": "sí",
        "favorite": "sí",
        "capture_date": "2026-01-15 10:30",
        "notes": "Mi primer Pokémon, ¡qué ilusión!",
    }


def test_csv_vacio_solo_cabecera(client, auth_headers):
    r = client.get(URL, headers=auth_headers)
    assert r.status_code == 200
    assert _filas_csv(r) == []
    assert r.content.decode("utf-8-sig").strip() == ",".join(COLUMNAS)


def test_csv_solo_lo_mio(client, auth_headers, test_user, other_user, add_to_pokedex):
    add_to_pokedex(test_user, 1)
    add_to_pokedex(other_user, 150)
    filas = _filas_csv(client.get(URL, headers=auth_headers))
    assert [f["pokemon_id"] for f in filas] == ["1"]


def test_csv_filtros(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 1, is_captured=True, favorite=True)
    add_to_pokedex(test_user, 4, is_captured=True)
    add_to_pokedex(test_user, 7, favorite=True)

    def ids(**params):
        r = client.get(URL, params=params, headers=auth_headers)
        return [f["pokemon_id"] for f in _filas_csv(r)]

    assert ids(captured=True) == ["1", "4"]
    assert ids(captured=False) == ["7"]
    assert ids(favorite=True) == ["1", "7"]
    assert ids(captured=True, favorite=True) == ["1"]


def test_csv_orden(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, 1, 7)  # pikachu, bulbasaur, squirtle
    r = client.get(
        URL, params={"sort": "pokemon_name", "order": "desc"}, headers=auth_headers
    )
    nombres = [f["pokemon_name"] for f in _filas_csv(r)]
    assert nombres == ["squirtle", "pikachu", "bulbasaur"]


def test_csv_exporta_todo_sin_paginar(client, auth_headers, test_user, add_to_pokedex):
    # El listado devuelve 20 por defecto; la exportación, todo.
    add_to_pokedex(test_user, *range(1, 31))
    assert len(_filas_csv(client.get(URL, headers=auth_headers))) == 30


def test_csv_neutraliza_formulas(client, auth_headers, test_user, add_to_pokedex):
    # Inyección CSV: una celda que empieza por = la ejecutaría Excel como fórmula.
    add_to_pokedex(test_user, 25, nickname='=HYPERLINK("http://malo")', notes="+1")
    (fila,) = _filas_csv(client.get(URL, headers=auth_headers))
    assert fila["nickname"] == '\'=HYPERLINK("http://malo")'
    assert fila["notes"] == "'+1"


def test_csv_comas_y_saltos_de_linea(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, notes='Dice "pika", y luego\notra línea')
    (fila,) = _filas_csv(client.get(URL, headers=auth_headers))
    assert fila["notes"] == 'Dice "pika", y luego\notra línea'


# ───────────────────────────── PDF ─────────────────────────────


def test_pdf(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, nickname="Pika", is_captured=True)
    add_to_pokedex(test_user, 1)
    r = client.get(URL, params={"format": "pdf"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="pokedex.pdf"'
    assert r.content.startswith(b"%PDF-")
    texto = _texto_pdf(r.content)
    assert "Pokédex de ash" in texto
    assert "pikachu" in texto and "Pika" in texto
    assert "bulbasaur" in texto
    assert "Total: 2" in texto and "Capturados: 1" in texto


def test_pdf_muestra_los_filtros(client, auth_headers, test_user, add_to_pokedex):
    add_to_pokedex(test_user, 25, is_captured=True)
    add_to_pokedex(test_user, 1)
    r = client.get(
        URL, params={"format": "pdf", "captured": True}, headers=auth_headers
    )
    texto = _texto_pdf(r.content)
    assert "captured=true" in texto
    assert "pikachu" in texto
    assert "bulbasaur" not in texto


def test_pdf_vacio(client, auth_headers):
    r = client.get(URL, params={"format": "pdf"}, headers=auth_headers)
    assert r.status_code == 200
    assert "No hay Pokémon" in _texto_pdf(r.content)


def test_pdf_muchas_entradas_ocupa_varias_paginas(
    client, auth_headers, test_user, add_to_pokedex
):
    add_to_pokedex(test_user, *range(1, 61))
    r = client.get(URL, params={"format": "pdf"}, headers=auth_headers)
    assert len(PdfReader(io.BytesIO(r.content)).pages) > 1


def test_pdf_caracteres_fuera_de_latin1_no_rompen(
    client, auth_headers, test_user, add_to_pokedex
):
    # Las fuentes básicas del PDF no tienen emojis: se cambian por «?», sin 500.
    add_to_pokedex(test_user, 25, nickname="Pika ⚡", notes="ピカチュウ")
    r = client.get(URL, params={"format": "pdf"}, headers=auth_headers)
    assert r.status_code == 200
    assert "Pika ?" in _texto_pdf(r.content)


# ───────────────────────────── Errores ─────────────────────────────


def test_formato_no_valido(client, auth_headers):
    r = client.get(URL, params={"format": "xlsx"}, headers=auth_headers)
    assert r.status_code == 422


def test_orden_no_valido(client, auth_headers):
    r = client.get(URL, params={"sort": "owner_id"}, headers=auth_headers)
    assert r.status_code == 422


def test_exportar_sin_token(client):
    assert client.get(URL).status_code == 401


def test_export_no_se_confunde_con_un_id(client, auth_headers):
    # /export va antes que /{entry_id}: no debe dar 422 por «export no es un int».
    assert client.get(URL, headers=auth_headers).status_code == 200


def test_exportar_limitado_a_10_por_minuto(client, auth_headers):
    for _ in range(10):
        assert client.get(URL, headers=auth_headers).status_code == 200
    assert client.get(URL, headers=auth_headers).status_code == 429


# ───────────────────────────── Servicio ─────────────────────────────


def test_servicio_csv_sin_entradas():
    assert pokedex_a_csv([]) == "﻿" + ",".join(COLUMNAS) + "\r\n"


def test_servicio_pdf_sin_filtros():
    texto = _texto_pdf(pokedex_a_pdf([], "misty", {}))
    assert "Filtros: ninguno" in texto
