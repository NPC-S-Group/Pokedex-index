"""Límite de longitud de las contraseñas, aparte para que models.py lo use sin
importar la configuración (app/auth.py necesita SECRET_KEY y models.py no).

bcrypt solo usa los primeros 72 bytes de la contraseña, y bcrypt >= 5 lanza
ValueError si recibe más: sin este límite, registro y login daban un error 500.
Son bytes, no caracteres: «ñ» o «é» ocupan 2 y un emoji 4.
"""

BCRYPT_MAX_BYTES = 72


def demasiado_larga(password: str) -> bool:
    return len(password.encode()) > BCRYPT_MAX_BYTES
