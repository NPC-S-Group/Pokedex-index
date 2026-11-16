"""Swagger (/docs): cada endpoint y cada grupo con su descripción en español (#52)."""

from app.main import app

# Nombres que FastAPI genera a partir de la función cuando falta «summary».
GENERADOS = {"Anadir", "Listar", "Detalle", "Borrar", "Crear", "Exportar", "Health"}


def _operaciones():
    for ruta, metodos in app.openapi()["paths"].items():
        for metodo, operacion in metodos.items():
            yield metodo.upper(), ruta, operacion


def test_todos_los_endpoints_tienen_resumen():
    sin_resumen = [
        (m, r) for m, r, op in _operaciones() if not op.get("summary")
    ]
    assert sin_resumen == []


def test_ningun_resumen_es_el_nombre_generado():
    generados = [(m, r, op["summary"]) for m, r, op in _operaciones() if op["summary"] in GENERADOS]
    assert generados == []


def test_resumenes_sin_repetir():
    # Antes había dos «Listar», dos «Detalle»… sin decir de qué grupo eran.
    resumenes = [op["summary"] for _, _, op in _operaciones()]
    assert len(resumenes) == len(set(resumenes))


def test_cada_grupo_tiene_descripcion():
    tags_usados = {t for _, _, op in _operaciones() for t in op.get("tags", [])}
    descritos = {t["name"] for t in app.openapi()["tags"] if t.get("description")}
    assert tags_usados <= descritos
