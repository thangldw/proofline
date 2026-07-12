from pathlib import Path


def test_compose_publishes_unauthenticated_api_to_loopback_by_default():
    repository = Path(__file__).resolve().parents[3]
    compose = (repository / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"${PROOFLINE_API_BIND:-127.0.0.1}:${PROOFLINE_API_PORT:-8000}:8000"' in compose
    assert '- "${PROOFLINE_API_PORT:-8000}:8000"' not in compose
