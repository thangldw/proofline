import json
import stat


def test_provider_configuration_persists_privately_and_never_returns_keys(
    client, monkeypatch, tmp_path
):
    path = tmp_path / "providers.json"
    monkeypatch.setenv("PROOFLINE_PROVIDER_CONFIG_PATH", str(path))
    for name in (
        "PROOFLINE_AI_PROVIDER",
        "PROOFLINE_AI_BASE_URL",
        "PROOFLINE_AI_MODEL",
        "PROOFLINE_AI_API_KEY",
        "PROOFLINE_EMBEDDING_PROVIDER",
        "PROOFLINE_EMBEDDING_BASE_URL",
        "PROOFLINE_EMBEDDING_MODEL",
        "PROOFLINE_EMBEDDING_API_KEY",
        "PROOFLINE_ALLOW_REMOTE_AI",
    ):
        monkeypatch.delenv(name, raising=False)
    payload = {
        "ai_provider": "qwen",
        "ai_model": "qwen-plus",
        "ai_api_key": "generation-secret",
        "embedding_provider": "ollama",
        "embedding_model": "nomic-embed-text",
        "embedding_api_key": "embedding-secret",
        "allow_remote_ai": True,
    }
    saved = client.put("/api/v1/model/configuration", json=payload)
    assert saved.status_code == 200
    assert saved.json()["ai_provider"] == "qwen"
    assert saved.json()["ai_api_key_configured"] is True
    assert "generation-secret" not in saved.text
    assert "embedding-secret" not in saved.text
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["ai_api_key"] == "generation-secret"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    readback = client.get("/api/v1/model/configuration")
    assert readback.status_code == 200
    assert "generation-secret" not in readback.text
    assert readback.json()["embedding_api_key_configured"] is True


def test_remote_profile_requires_explicit_egress_and_rolls_back(client, monkeypatch, tmp_path):
    path = tmp_path / "providers.json"
    monkeypatch.setenv("PROOFLINE_PROVIDER_CONFIG_PATH", str(path))
    for name in (
        "PROOFLINE_AI_PROVIDER",
        "PROOFLINE_EMBEDDING_PROVIDER",
        "PROOFLINE_ALLOW_REMOTE_AI",
    ):
        monkeypatch.delenv(name, raising=False)
    response = client.put(
        "/api/v1/model/configuration",
        json={
            "ai_provider": "deepseek",
            "embedding_provider": "disabled",
            "allow_remote_ai": False,
        },
    )
    assert response.status_code == 422
    assert not path.exists() or json.loads(path.read_text(encoding="utf-8")) == {}
