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


def test_health_sin_render_no_dice_el_commit(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    with TestClient(app) as cliente:
        assert "commit" not in cliente.get("/health").json()


def test_health_en_render_dice_el_commit(monkeypatch):
    # El CI compara este valor con el commit recién fusionado en main.
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    with TestClient(app) as cliente:
        assert cliente.get("/health").json() == {"status": "ok", "commit": "abc123"}
