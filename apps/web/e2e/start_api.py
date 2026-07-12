from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

WEB_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = WEB_ROOT.parents[1]
DATABASE_PATH = WEB_ROOT / ".proofline-e2e.db"


def main() -> None:
    for suffix in ("", "-shm", "-wal"):
        DATABASE_PATH.with_name(f"{DATABASE_PATH.name}{suffix}").unlink(missing_ok=True)

    os.environ["PROOFLINE_DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"
    os.environ.setdefault("PROOFLINE_AI_PROVIDER", "disabled")
    os.environ.setdefault("PROOFLINE_EMBEDDING_PROVIDER", "disabled")
    os.environ.setdefault("PROOFLINE_ALLOW_REMOTE_AI", "false")
    sys.path.insert(0, str(REPOSITORY_ROOT / "apps" / "api"))

    from proofline.main import app

    port = int(os.environ.get("PROOFLINE_E2E_API_PORT", "8765"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
