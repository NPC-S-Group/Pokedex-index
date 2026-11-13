"""Logs también en archivo (#15, mejora sobre #10)."""

import logging
from logging.handlers import RotatingFileHandler

import pytest

from app.config import Settings
from app.logs import configurar_logging


@pytest.fixture
def sin_manejadores_de_archivo():
    """Deja el logger como estaba: quita los manejadores de archivo que añada el test."""
    logger_api = logging.getLogger("pokedex_api")
    antes = list(logger_api.handlers)
    yield logger_api
    for h in logger_api.handlers:
        if h not in antes:
            logger_api.removeHandler(h)
            h.close()


def _de_archivo(logger_api):
    return [h for h in logger_api.handlers if isinstance(h, RotatingFileHandler)]


def test_escribe_en_el_archivo(tmp_path, sin_manejadores_de_archivo):
    archivo = tmp_path / "api.log"
    configurar_logging("INFO", str(archivo))
    logging.getLogger("pokedex_api.prueba").info("hola desde el test")
    for h in _de_archivo(sin_manejadores_de_archivo):
        h.flush()
    contenido = archivo.read_text(encoding="utf-8")
    assert "hola desde el test" in contenido
    assert "pokedex_api.prueba" in contenido


def test_no_duplica_el_manejador(tmp_path, sin_manejadores_de_archivo):
    archivo = str(tmp_path / "api.log")
    configurar_logging("INFO", archivo)
    configurar_logging("INFO", archivo)
    rutas = [h.baseFilename for h in _de_archivo(sin_manejadores_de_archivo)]
    assert rutas.count(str(tmp_path / "api.log")) == 1


def test_sin_archivo_solo_consola(tmp_path, sin_manejadores_de_archivo):
    antes = len(_de_archivo(sin_manejadores_de_archivo))
    configurar_logging("INFO", "")
    configurar_logging("INFO", None)
    assert len(_de_archivo(sin_manejadores_de_archivo)) == antes


def test_rota_al_llegar_al_limite(tmp_path, sin_manejadores_de_archivo):
    configurar_logging("INFO", str(tmp_path / "api.log"))
    (manejador,) = [
        h for h in _de_archivo(sin_manejadores_de_archivo)
        if h.baseFilename == str(tmp_path / "api.log")
    ]
    assert manejador.maxBytes == 1_000_000 and manejador.backupCount == 3


def test_config_por_defecto_y_desactivado(monkeypatch):
    monkeypatch.delenv("LOG_FILE", raising=False)
    assert Settings(_env_file=None).log_file == "pokedex_api.log"
    monkeypatch.setenv("LOG_FILE", "")
    assert not Settings(_env_file=None).log_file
