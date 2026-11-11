from fastapi.testclient import TestClient

from app.main import app


def test_health_responde_ok():
    with TestClient(app) as cliente:
        respuesta = cliente.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}


def test_docs_disponible():
    with TestClient(app) as cliente:
        assert cliente.get("/docs").status_code == 200
