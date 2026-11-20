# Proofline for Claude Code

Evidence-first decision memory for coding agents. Approved decisions are shown before an edit, and their `Enforce:` rules are checked after it. A new dependency or infrastructure file with no decision behind it gets a draft-ADR suggestion.

## What it does and what data it sends

- Two hooks (`PreToolUse` and `PostToolUse` on `Edit|Write|MultiEdit`) run `proofline agent-hook pre|post` on your machine. They are silent unless the project has a `.proofline/proofline.db` and the `proofline` CLI is installed.
- Nothing is sent over the network. Proofline is local-first and the hooks read only your project's local decision database and the file being edited.
- One skill, `manage-evidence-decisions`, verifies evidence packages and explains citations with no AI provider.

## Install

```bash
pipx install proofline-evidence
/plugin marketplace add thangldw/proofline
/plugin install proofline@proofline
```

Documentation: https://github.com/thangldw/proofline/blob/main/docs/mcp.md. Licensed under Apache-2.0.
