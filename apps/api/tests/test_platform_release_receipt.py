import json
import subprocess
import sys
from pathlib import Path

from proofline import __version__


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_platform_release_receipt_qualifies_identified_installed_artifact(tmp_path):
    artifact = tmp_path / "proofline-test-artifact.whl"
    artifact.write_bytes(b"synthetic wheel identity for receipt test")
    output = tmp_path / "platform-receipt.json"
    executable = Path(sys.executable).with_name("proofline")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/platform_release_receipt.py",
            "--proofline",
            str(executable),
            "--python",
            sys.executable,
            "--artifact",
            str(artifact),
            "--expected-version",
            __version__,
            "--output",
            str(output),
        ],
        cwd=repository_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    stdout = json.loads(completed.stdout)
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt == stdout
    assert receipt["schema_version"] == "proofline.platform-release-qualification.v1"
    assert receipt["artifact"]["name"] == artifact.name
    assert len(receipt["artifact"]["sha256"]) == 64
    assert receipt["lifecycle"]["graceful_shutdown"] is True
    assert receipt["recovery"]["source_versions"] == 2
    assert receipt["integrity"]["valid"] is True
    assert receipt["os_keyring"] == {"status": "not_run"}
    assert "another OS" in receipt["qualification"]


def test_platform_release_receipt_refuses_overwrite(tmp_path):
    artifact = tmp_path / "artifact.whl"
    artifact.write_bytes(b"artifact")
    output = tmp_path / "receipt.json"
    output.write_text("existing", encoding="utf-8")
    executable = Path(sys.executable).with_name("proofline")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/platform_release_receipt.py",
            "--proofline",
            str(executable),
            "--python",
            sys.executable,
            "--artifact",
            str(artifact),
            "--expected-version",
            __version__,
            "--output",
            str(output),
        ],
        cwd=repository_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert output.read_text(encoding="utf-8") == "existing"
