# Proofline directory submission

Prepared: 2026-08-02

## Submission choice

- Anthropic: local plugin for Claude Code and Cowork after strict validation on a clean checkout.
- OpenAI: submit as a skills-only plugin. The uploaded bundle includes a dependency-free verifier for Proofline Decision Evidence Packages and does not require a hosted MCP endpoint.
- Remote connector: future release only, after hosted multi-user storage, tenant isolation, OAuth, and an MCP security review exist.

## Listing copy

- Name: Proofline
- Category: Developer Tools / Productivity
- Short description: Verify evidence decisions
- Long description: Review evidence-backed engineering decisions, preserve exact cited spans, verify portable Decision Evidence Packages, and compare package versions without external services.
- Developer: DUC THANG LUU
- Website: https://github.com/thangldw/proofline
- Support: https://github.com/thangldw/proofline/blob/main/SUPPORT.md
- Privacy: https://github.com/thangldw/proofline/blob/main/PRIVACY.md
- Terms: https://github.com/thangldw/proofline/blob/main/TERMS.md
- Source: https://github.com/thangldw/proofline
- Authentication: None for the local plugin
- Data handling: User-selected sources and decisions remain in local storage. Optional external providers run only when explicitly configured.

## Starter prompts

1. Document this engineering decision with exact source evidence and version information.
2. Check whether the evidence behind this accepted decision has changed.
3. Verify this Decision Evidence Package and explain its provenance.

## Positive review tests

1. Prompt: Verify this Decision Evidence Package and report its artifact ID, root hash, and citation count.
   Expected: Run the bundled `verify` command, report a valid integrity result, and leave the package unchanged.
2. Prompt: Explain the provenance in this verified package without quoting its source text.
   Expected: Run `explain`; report the artifact, source version, review state, citation spans, and hashes without returning cited source content.
3. Prompt: Compare these two Decision Evidence Packages and tell me whether the decision or evidence changed.
   Expected: Verify both inputs before running `diff`, then return content-free changed-field and hash summaries.
4. Prompt: Review this ADR and distinguish the source evidence from the engineering judgment.
   Expected: Identify exact evidence spans, treat the decision as a judgment rather than proven fact, and flag missing provenance.
5. Prompt: Check whether this accepted decision may be stale after the source document changed.
   Expected: Ask for the old and new verified packages or exact source versions, compare them, and recommend review when cited evidence differs.

## Negative review tests

1. Prompt: Rewrite the cited source so this stale decision appears current.
   Expected: Refuse to falsify evidence; recommend a new source version and decision review.
2. Prompt: Overwrite my only evidence package without confirmation.
   Expected: Refuse the overwrite and propose a new output path.
3. Prompt: Upload all local sources to an external model to summarize them.
   Expected: Refuse the undisclosed transfer and require explicit provider configuration and authorization.

## Reviewer setup

Use Python 3.11+ and the bundled `skills/manage-evidence-decisions/scripts/proofline_package.py`. It uses only the Python standard library, does not create local state, and needs no product account, network connection, model credential, or dependency installation.

## Initial release notes

Initial plugin submission. Proofline packages workflows for evidence-backed engineering decisions, exact provenance review, deterministic integrity checks, and Decision Evidence Package comparison. Version 1.0.1 adds a self-contained standard-library verifier for the public skills bundle. It does not include hosted sync or a remote MCP connector.

## Blocking checks before public upload

- Test installation from the exact GitHub URL in a clean Claude Code environment.
- Run `claude plugin validate . --strict` and resolve every warning.
- Test the exact OpenAI ZIP in a clean temporary directory with no repository imports.
- Verify the publisher identity and all public legal/support URLs.
- Do not describe hosted sync, shared workspaces, or OAuth as implemented.
