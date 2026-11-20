#!/bin/sh
# Proofline post-edit hook. Silent unless the proofline CLI is installed; never fails the session.
command -v proofline >/dev/null 2>&1 || exit 0
proofline agent-hook post || true
