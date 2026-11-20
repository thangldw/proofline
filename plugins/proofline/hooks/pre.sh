#!/bin/sh
# Proofline pre-edit hook. Silent unless the proofline CLI is installed; never fails the session.
command -v proofline >/dev/null 2>&1 || exit 0
proofline agent-hook pre || true
