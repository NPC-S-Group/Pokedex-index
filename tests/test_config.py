"""Configuración: la SECRET_KEY tiene que ser larga y no la de ejemplo."""

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    "clave",
    [
        "x",
        "corta-de-31-caracteres-123456789"[:31],
        "pon-aqui-una-clave-larga-y-aleatoria",  # la del .env.example antiguo
        "pon-aqui-una-clave-aleatoria-de-al-menos-32-caracteres",  # la actual
    ],
)
def test_secret_key_no_valida(clave):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, secret_key=clave)


def test_secret_key_de_32_caracteres():
    assert Settings(_env_file=None, secret_key="a" * 32).secret_key == "a" * 32
