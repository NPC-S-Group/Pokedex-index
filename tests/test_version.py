"""La versión que muestra /docs es la misma que la de pyproject.toml.

Hasta la v1.0.3, /docs decía «1.0.0» en todas las versiones porque nadie la
cambiaba. Este test falla si se sube una y se olvida la otra.
"""

import tomllib
from pathlib import Path

from app.main import app


def test_la_version_de_la_api_coincide_con_pyproject():
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    version = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert app.version == version


def test_la_version_sale_en_openapi(client):
    assert client.get("/openapi.json").json()["info"]["version"] == app.version
