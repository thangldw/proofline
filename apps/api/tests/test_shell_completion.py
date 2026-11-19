import shutil
import subprocess

import pytest
from proofline.cli import main


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_lists_commands_and_options(shell, capsys):
    main(["completion", shell])
    text = capsys.readouterr().out
    for command in ("import-adr", "hook", "report", "check-decisions", "completion"):
        assert command in text
    assert "output-dir" in text and "no-titles" in text


def test_bash_script_has_valid_syntax_and_completes(capsys, tmp_path):
    main(["completion", "bash"])
    script = tmp_path / "c.bash"
    script.write_text(capsys.readouterr().out)
    bash = shutil.which("bash")
    assert bash
    assert subprocess.run([bash, "-n", str(script)]).returncode == 0
    probe = (
        f"source {script}; COMP_WORDS=(proofline hoo); COMP_CWORD=1; _proofline; "
        'echo "${COMPREPLY[@]}"'
    )
    result = subprocess.run([bash, "-c", probe], capture_output=True, text=True)
    assert result.stdout.split() == ["hook"]
    probe = (
        f"source {script}; COMP_WORDS=(proofline hook ins); COMP_CWORD=2; _proofline; "
        'echo "${COMPREPLY[@]}"'
    )
    result = subprocess.run([bash, "-c", probe], capture_output=True, text=True)
    assert "install" in result.stdout.split()


def test_zsh_and_fish_scripts_parse_when_shells_exist(capsys, tmp_path):
    for shell, flag in (("zsh", "-n"), ("fish", "--no-execute")):
        exe = shutil.which(shell)
        if exe is None:
            continue
        main(["completion", shell])
        script = tmp_path / f"c.{shell}"
        script.write_text(capsys.readouterr().out)
        assert subprocess.run([exe, flag, str(script)]).returncode == 0
