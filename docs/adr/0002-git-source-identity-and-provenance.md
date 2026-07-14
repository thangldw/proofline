# ADR 0002: Local Git source identity

Status: accepted and implemented.

An explicitly registered local repository is read at a resolved commit. Git file identity combines
repository identity, commit SHA, and tracked path; commit metadata uses the repository identity and
commit SHA. Content at an imported commit is immutable even after the working tree changes.

Only tracked text files and bounded commit metadata enter the index. Network clone, OAuth, webhook,
pull-request automation, and write-back are outside this decision. Re-scan is idempotent and source
deletion cascades through all derived records.
