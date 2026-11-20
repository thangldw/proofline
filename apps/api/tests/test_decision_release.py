import copy
import json
import subprocess
from datetime import UTC, datetime

import proofline.cli as cli_module
import pytest
from proofline.attestations import (
    AttestationError,
    generate_attestation_keypair,
    load_attestation_private_key,
    load_attestation_public_key,
)
from proofline.cli import main
from proofline.decision_release import (
    build_release_attestation,
    collect_state,
    load_and_verify_release,
    verify_release_attestation,
)
from proofline.ingestion import ingest_source
from proofline.models import Decision
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
ADR = 'Decision: Core stays offline.\nEnforce: forbid "import requests" in src/**/*.py\n'


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, session):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x = 1\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    source, _ = ingest_source(
        session, SourceCreate(title="adr", uri="file:///r/adr.md", content=ADR)
    )
    for decision in session.scalars(select(Decision).where(Decision.source_id == source.id)):
        decision.status = "accepted"
    session.commit()
    return root


@pytest.fixture
def keys(tmp_path):
    generate_attestation_keypair(tmp_path / "k.pem", tmp_path / "k.pub")
    return tmp_path / "k.pem", tmp_path / "k.pub"


def test_clean_state_is_signed_and_verifies(session, repo, keys):
    state = collect_state(session, repo, None, tag="v1.0.0")
    assert state["compliant"] and state["dirty"] is False and state["ledger_head"] is None
    assert state["decisions"]["approved"] == 1 and len(state["commit"]) == 40
    private = load_attestation_private_key(keys[0])
    document = build_release_attestation(state, private, NOW)
    report = verify_release_attestation(
        document, load_attestation_public_key(keys[1]), expected_commit=state["commit"]
    )
    assert report["valid"] and report["compliant"] and report["tag"] == "v1.0.0"
    assert "Core stays offline" not in json.dumps(document), "the attestation is content-free"


def test_violation_is_recorded_truthfully_and_not_compliant(session, repo, keys):
    (repo / "src" / "a.py").write_text("import requests\n")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "bad")
    state = collect_state(session, repo, None, tag=None)
    assert state["decisions"]["enforcement_findings"] == 1 and state["compliant"] is False


def test_dirty_tree_is_reported(session, repo):
    (repo / "src" / "a.py").write_text("x = 2\n")
    assert collect_state(session, repo, None, tag=None)["dirty"] is True


def test_tampering_wrong_key_commit_revocation_and_shape_are_rejected(
    session, repo, keys, tmp_path
):
    state = collect_state(session, repo, None, tag=None)
    private = load_attestation_private_key(keys[0])
    public = load_attestation_public_key(keys[1])
    document = build_release_attestation(state, private, NOW)

    forged = copy.deepcopy(document)
    forged["statement"]["decisions"]["stale"] = 3
    with pytest.raises(AttestationError, match="compliant_inconsistent"):
        verify_release_attestation(forged, public)
    forged = copy.deepcopy(document)
    forged["statement"]["commit"] = "0" * 40
    with pytest.raises(AttestationError, match="signature_invalid"):
        verify_release_attestation(forged, public)
    with pytest.raises(AttestationError, match="commit_mismatch"):
        verify_release_attestation(document, public, expected_commit="1" * 40)
    with pytest.raises(AttestationError, match="key_revoked"):
        verify_release_attestation(
            document, public, revoked_key_ids=frozenset({document["key_id"]})
        )
    generate_attestation_keypair(tmp_path / "o.pem", tmp_path / "o.pub")
    with pytest.raises(AttestationError, match="key_id_mismatch"):
        verify_release_attestation(document, load_attestation_public_key(tmp_path / "o.pub"))
    for mutate, code in [
        (lambda d: d.update(schema="x"), "schema_unsupported"),
        (lambda d: d.pop("signature"), "attestation_shape_invalid"),
        (lambda d: d["statement"].update(commit="zz"), "commit_invalid"),
        (lambda d: d["statement"].update(tag="a b"), "tag_invalid"),
        (lambda d: d["statement"].update(dirty="no"), "flags_invalid"),
        (lambda d: d["statement"]["decisions"].update(approved=-1), "decisions_invalid"),
        (lambda d: d["statement"].update(ledger_head="short"), "ledger_head_invalid"),
        (lambda d: d["statement"].update(extra=1), "statement_shape_invalid"),
        (lambda d: d.update(signature="!!"), "signature_encoding_invalid"),
    ]:
        broken = copy.deepcopy(document)
        mutate(broken)
        with pytest.raises(AttestationError, match=code):
            verify_release_attestation(broken, public)
    with pytest.raises(AttestationError, match="tag_invalid"):
        collect_state(session, repo, None, tag="bad tag")
    missing = tmp_path / "none.json"
    with pytest.raises(AttestationError, match="attestation_unreadable"):
        load_and_verify_release(missing, public)


def test_cli_roundtrip_gate_and_errors(session, repo, keys, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    out = tmp_path / "release.json"
    common = ["--private-key", str(keys[0]), "--root", str(repo), "--output", str(out)]
    main(["attest-release", *common, "--tag", "v1.0.0", "--issued-at", "2026-11-20T12:00:00+00:00"])
    assert json.loads(capsys.readouterr().out)["compliant"] is True
    main(
        [
            "verify-release-attestation",
            str(out),
            "--public-key",
            str(keys[1]),
            "--require-compliant",
        ]
    )
    assert json.loads(capsys.readouterr().out)["tag"] == "v1.0.0"
    with pytest.raises(SystemExit, match="output_exists"):
        main(["attest-release", *common])
    with pytest.raises(SystemExit, match="commit_mismatch"):
        main(
            [
                "verify-release-attestation",
                str(out),
                "--public-key",
                str(keys[1]),
                "--commit",
                "2" * 40,
            ]
        )
    (repo / "src" / "a.py").write_text("import requests\n")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "bad")
    with pytest.raises(SystemExit, match="not_compliant"):
        main(["attest-release", *common, "--require-compliant", "--force"])
    main(["attest-release", *common, "--force"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as caught:
        main(
            [
                "verify-release-attestation",
                str(out),
                "--public-key",
                str(keys[1]),
                "--require-compliant",
            ]
        )
    assert caught.value.code == 1
    (repo / "src" / "a.py").write_text("dirty\n")
    with pytest.raises(SystemExit, match="worktree_dirty"):
        main(["attest-release", *common, "--force"])
    capsys.readouterr()
    main(["attest-release", *common, "--force", "--allow-dirty"])
    assert json.loads(capsys.readouterr().out)["compliant"] is False
