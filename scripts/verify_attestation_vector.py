#!/usr/bin/env python3
"""Verify the tracked Proofline Ed25519 attestation conformance vector."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from proofline.attestations import load_and_verify_attestation, load_attestation_public_key


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_attestation_vector.py ATTESTATION PUBLIC_KEY")
    _document, report = load_and_verify_attestation(
        Path(sys.argv[1]),
        load_attestation_public_key(Path(sys.argv[2])),
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
