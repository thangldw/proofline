import json
import stat

from proofline import secret_store


class FakeSecretStore:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


def clear_provider_environment(monkeypatch):
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


def test_provider_configuration_persists_privately_and_never_returns_keys(
    client, monkeypatch, tmp_path
):
    path = tmp_path / "providers.json"
    monkeypatch.setenv("PROOFLINE_PROVIDER_CONFIG_PATH", str(path))
    clear_provider_environment(monkeypatch)
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
    assert readback.json()["secret_storage"] == "owner_only_file"


def test_os_keyring_configuration_migrates_legacy_keys_and_keeps_json_secret_free(
    client, monkeypatch, tmp_path
):
    path = tmp_path / "providers.json"
    path.write_text(
        json.dumps(
            {
                "ai_provider": "ollama",
                "ai_api_key": "legacy-generation-secret",
                "embedding_provider": "disabled",
            }
        ),
        encoding="utf-8",
    )
    store = FakeSecretStore()
    monkeypatch.setenv("PROOFLINE_PROVIDER_CONFIG_PATH", str(path))
    monkeypatch.setenv("PROOFLINE_SECRET_STORE", "os_keyring")
    monkeypatch.setattr(secret_store, "get_provider_secret_store", lambda _path: store)
    clear_provider_environment(monkeypatch)

    saved = client.put(
        "/api/v1/model/configuration",
        json={
            "ai_provider": "ollama",
            "embedding_provider": "disabled",
            "allow_remote_ai": False,
        },
    )

    assert saved.status_code == 200
    assert saved.json()["secret_storage"] == "os_keyring"
    assert saved.json()["ai_api_key_configured"] is True
    assert store.values == {"ai_api_key": "legacy-generation-secret"}
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert "ai_api_key" not in stored
    assert "embedding_api_key" not in stored
    assert "legacy-generation-secret" not in path.read_text(encoding="utf-8")


def test_os_keyring_key_can_be_replaced_and_removed(client, monkeypatch, tmp_path):
    path = tmp_path / "providers.json"
    store = FakeSecretStore({"ai_api_key": "old-secret"})
    monkeypatch.setenv("PROOFLINE_PROVIDER_CONFIG_PATH", str(path))
    monkeypatch.setenv("PROOFLINE_SECRET_STORE", "os_keyring")
    monkeypatch.setattr(secret_store, "get_provider_secret_store", lambda _path: store)
    clear_provider_environment(monkeypatch)

    replaced = client.put(
        "/api/v1/model/configuration",
        json={
            "ai_provider": "ollama",
            "ai_api_key": "new-secret",
            "embedding_provider": "disabled",
        },
    )
    assert replaced.status_code == 200
    assert store.values["ai_api_key"] == "new-secret"

    removed = client.put(
        "/api/v1/model/configuration",
        json={
            "ai_provider": "ollama",
            "ai_api_key": "",
            "embedding_provider": "disabled",
        },
    )
    assert removed.status_code == 200
    assert "ai_api_key" not in store.values
    assert removed.json()["ai_api_key_configured"] is False


def test_os_keyring_and_file_roll_back_together_for_invalid_provider(client, monkeypatch, tmp_path):
    path = tmp_path / "providers.json"
    original = {
        "ai_provider": "ollama",
        "embedding_provider": "disabled",
        "allow_remote_ai": False,
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    store = FakeSecretStore({"ai_api_key": "old-secret"})
    monkeypatch.setenv("PROOFLINE_PROVIDER_CONFIG_PATH", str(path))
    monkeypatch.setenv("PROOFLINE_SECRET_STORE", "os_keyring")
    monkeypatch.setattr(secret_store, "get_provider_secret_store", lambda _path: store)
    clear_provider_environment(monkeypatch)

    response = client.put(
        "/api/v1/model/configuration",
        json={
            "ai_provider": "openai_compatible",
            "ai_api_key": "replacement-secret",
            "embedding_provider": "disabled",
            "allow_remote_ai": False,
        },
    )

    assert response.status_code == 422
    assert json.loads(path.read_text(encoding="utf-8")) == original
    assert store.values == {"ai_api_key": "old-secret"}


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
