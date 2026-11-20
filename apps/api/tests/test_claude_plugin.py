import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest
from proofline.cli import main

ROOT = Path(__file__).resolve().parents[3]


def _json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_plugin_and_marketplace_agree_with_the_package_version():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    plugin = _json(".claude-plugin/plugin.json")
    marketplace = _json(".claude-plugin/marketplace.json")
    assert plugin["name"] == "proofline" and plugin["version"] == version
    [entry] = marketplace["plugins"]
    assert entry["name"] == plugin["name"] and entry["version"] == version
    assert entry["source"] == "./"
    assert "hooks" not in plugin, "hooks/hooks.json is loaded by convention; naming it duplicates"


def test_hooks_only_call_the_agent_hook_and_never_fail_the_session():
    hooks = _json("hooks/hooks.json")["hooks"]
    assert set(hooks) == {"PreToolUse", "PostToolUse"}
    phases = {"PreToolUse": "pre", "PostToolUse": "post"}
    for event, groups in hooks.items():
        [group] = groups
        assert group["matcher"] == "Edit|Write|MultiEdit"
        [hook] = group["hooks"]
        assert hook["type"] == "command" and hook["timeout"] <= 30
        assert hook["command"].endswith(f"proofline agent-hook {phases[event]} || true")
        assert "command -v proofline" in hook["command"]


def test_registered_hook_commands_exist_in_the_cli(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["agent-hook", "sideways"])
    assert caught.value.code == 2
    capsys.readouterr()
    for phase in ("pre", "post"):
        with pytest.raises(SystemExit):
            main(["agent-hook", phase, "--help"])
        assert "usage:" in capsys.readouterr().out


@pytest.mark.parametrize("phase", ["pre", "post"])
def test_hook_command_is_silent_without_the_cli_and_forwards_when_present(phase, tmp_path):
    command = next(
        hook["command"]
        for groups in _json("hooks/hooks.json")["hooks"].values()
        for group in groups
        for hook in group["hooks"]
        if hook["command"].endswith(f"agent-hook {phase} || true")
    )
    bare = {**os.environ, "PATH": "/usr/bin:/bin"}
    absent = subprocess.run(
        ["sh", "-c", command], capture_output=True, text=True, env=bare, input="{}", cwd=tmp_path
    )
    assert absent.returncode == 0 and absent.stdout == "" and absent.stderr == ""
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "proofline").write_text('#!/bin/sh\necho "called $@"\nexit 7\n')
    (stub / "proofline").chmod(0o755)
    present = subprocess.run(
        ["sh", "-c", command],
        capture_output=True,
        text=True,
        env={**bare, "PATH": f"{stub}:/usr/bin:/bin"},
        input="{}",
        cwd=tmp_path,
    )
    assert present.returncode == 0 and present.stdout.strip() == f"called agent-hook {phase}"
