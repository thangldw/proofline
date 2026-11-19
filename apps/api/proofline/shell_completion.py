from __future__ import annotations

import argparse
import shlex


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _options(parser: argparse.ArgumentParser) -> list[str]:
    found: list[str] = []
    for action in parser._actions:
        found.extend(item for item in action.option_strings if item.startswith("--"))
    return sorted(set(found))


def _tree(parser: argparse.ArgumentParser) -> dict[str, tuple[list[str], list[str]]]:
    """Map each top-level command to its (options, nested subcommand names)."""

    return {
        name: (_options(child), sorted(_subparsers(child)))
        for name, child in sorted(_subparsers(parser).items())
    }


def _zsh_arguments(options: list[str], nested: list[str]) -> str:
    parts = [shlex.quote(option) for option in options]
    if nested:
        parts.append(shlex.quote(f"1:action:({' '.join(nested)})"))
    parts.append("'*:file:_files'")
    return " ".join(parts)


def render_completion(parser: argparse.ArgumentParser, shell: str) -> str:
    tree = _tree(parser)
    names = " ".join(tree)
    if shell == "bash":
        cases = "\n".join(
            f"    {name}) opts={shlex.quote(' '.join(sub or opts))} ;;"
            if sub
            else f"    {name}) opts={shlex.quote(' '.join(opts))} ;;"
            for name, (opts, sub) in tree.items()
        )
        return (
            "# bash completion for proofline\n"
            "_proofline() {\n"
            '  local cur="${COMP_WORDS[COMP_CWORD]}" cmd="${COMP_WORDS[1]}" opts\n'
            '  if [ "$COMP_CWORD" -eq 1 ]; then\n'
            f'    COMPREPLY=($(compgen -W {shlex.quote(names + " --version --help")} -- "$cur"))\n'
            "    return\n"
            "  fi\n"
            '  case "$cmd" in\n'
            f"{cases}\n"
            '    *) opts="" ;;\n'
            "  esac\n"
            '  COMPREPLY=($(compgen -W "$opts --help" -f -- "$cur"))\n'
            "}\n"
            "complete -o filenames -F _proofline proofline\n"
        )
    if shell == "zsh":
        cases = "\n".join(
            f"    {name}) _arguments {_zsh_arguments(opts, sub)} ;;"
            for name, (opts, sub) in tree.items()
        )
        return (
            "#compdef proofline\n"
            "_proofline() {\n"
            f"  local -a commands=({names})\n"
            "  if (( CURRENT == 2 )); then\n"
            "    _describe 'command' commands\n"
            "    return\n"
            "  fi\n"
            '  case "$words[2]" in\n'
            f"{cases}\n"
            "  esac\n"
            "}\n"
            '_proofline "$@"\n'
        )
    if shell == "fish":
        lines = ["# fish completion for proofline", "complete -c proofline -f"]
        for name, (opts, sub) in tree.items():
            lines.append(f"complete -c proofline -n '__fish_use_subcommand' -a {shlex.quote(name)}")
            lines.extend(
                f"complete -c proofline -n '__fish_seen_subcommand_from {name}' -l {opt[2:]}"
                for opt in opts
            )
            lines.extend(
                f"complete -c proofline -n '__fish_seen_subcommand_from {name}' "
                f"-a {shlex.quote(item)}"
                for item in sub
            )
        return "\n".join(lines) + "\n"
    raise ValueError("shell_unsupported")
