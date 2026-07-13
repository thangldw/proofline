from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ingestion import IngestionConflict, IngestionExecutionError, run_ingestion_job
from .models import GitRepository, Source, utc_now
from .schemas import GitRepositoryCreate, SourceCreate

SUPPORTED_SUFFIXES = {".md": "git_file", ".markdown": "git_file", ".txt": "git_file"}
MAX_GIT_FILE_BYTES = 5_000_000


class GitIngestionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _git(path: Path, *args: str, text: bool = True) -> str | bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), *args],
            check=True,
            capture_output=True,
            text=text,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitIngestionError("git_command_failed", "Git could not read the repository.") from exc
    return completed.stdout


def import_git_repository(
    session: Session, payload: GitRepositoryCreate
) -> tuple[GitRepository, str, int, int, list[dict[str, str]]]:
    try:
        path = Path(payload.path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise GitIngestionError(
            "repository_unavailable", "Repository path is unavailable."
        ) from exc
    if not path.is_dir() or _git(path, "rev-parse", "--is-inside-work-tree").strip() != "true":
        raise GitIngestionError("not_a_git_repository", "Path is not a Git work tree.")
    root = Path(str(_git(path, "rev-parse", "--show-toplevel")).strip()).resolve()
    if root != path:
        raise GitIngestionError("repository_root_required", "Register the Git repository root.")
    commit_sha = str(_git(root, "rev-parse", "--verify", f"{payload.revision}^{{commit}}")).strip()
    canonical_path = str(root)
    repository = session.scalar(select(GitRepository).where(GitRepository.path == canonical_path))
    if repository is None:
        repository = GitRepository(title=payload.title or root.name, path=canonical_path)
        session.add(repository)
        session.commit()

    entries = str(_git(root, "ls-tree", "-r", "--name-only", "-z", commit_sha)).split("\0")
    paths = [item for item in entries if Path(item).suffix.casefold() in SUPPORTED_SUFFIXES]
    author = str(_git(root, "show", "-s", "--format=%an <%ae>", commit_sha)).rstrip("\n")
    authored_at = str(_git(root, "show", "-s", "--format=%aI", commit_sha)).strip()
    subject = str(_git(root, "show", "-s", "--format=%s", commit_sha)).rstrip("\n")
    body = str(_git(root, "show", "-s", "--format=%b", commit_sha)).rstrip("\n")
    items = [
        (
            "git_commit",
            f"Commit {commit_sha[:12]}",
            "__commit__",
            "\n".join(
                [
                    f"Commit: {commit_sha}",
                    f"Author: {author}",
                    f"Authored: {authored_at}",
                    f"Subject: {subject}",
                    "",
                    body,
                ]
            ).rstrip(),
        )
    ]
    failures: list[dict[str, str]] = []
    for file_path in paths:
        raw = _git(root, "show", f"{commit_sha}:{file_path}", text=False)
        if len(raw) > MAX_GIT_FILE_BYTES:
            failures.append({"path": file_path, "error_code": "git_file_too_large"})
            continue
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            failures.append({"path": file_path, "error_code": "git_file_encoding_invalid"})
            continue
        if not content:
            failures.append({"path": file_path, "error_code": "git_file_empty"})
            continue
        items.append(("git_file", file_path, file_path, content))

    created_count = unchanged_count = 0
    for kind, title, locator, content in items:
        uri = f"git+file://{root.as_posix()}?commit={commit_sha}#path={locator}"
        existing = session.scalar(select(Source).where(Source.uri == uri))
        try:
            source, created, _job = run_ingestion_job(
                session,
                SourceCreate(title=title[:300], content=content, kind="text", uri=uri),
            )
        except (IngestionConflict, IngestionExecutionError):
            failures.append({"path": locator, "error_code": "git_source_ingestion_failed"})
            continue
        source.kind = kind
        source.git_repository_id = repository.id
        source.git_commit_sha = commit_sha
        source.git_path = None if kind == "git_commit" else locator
        session.commit()
        created_count += int(created and existing is None)
        unchanged_count += int(not created or existing is not None)
    repository.current_commit_sha = commit_sha
    repository.indexed_at = utc_now()
    repository.status = "degraded" if failures else "indexed"
    session.commit()
    return repository, commit_sha, created_count, unchanged_count, failures
