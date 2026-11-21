from fastapi.testclient import TestClient

from gartic_helper.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_guess_with_pattern_only_uses_word_list() -> None:
    response = client.post("/guess", json={"hint_pattern": "a_l__", "max_candidates": 5})
    assert response.status_code == 200
    body = response.json()
    assert "aslan" in body["candidates"]
    assert body["used_model"] is False
