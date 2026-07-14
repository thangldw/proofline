# ADR 0003: Defer Tauri desktop packaging

- Status: superseded by the experimental v0.14.15 desktop implementation
- Date: 2026-07-13

## Context

Proofline now has a usable local API/web vertical slice, workspace isolation, deterministic
portability and release artifacts. The remaining roadmap still lacks a verified Windows run,
production qualification, an embedded API lifecycle contract, signed installers, auto-update and a
defined support boundary. Wrapping the current two-process development topology would create a new
distribution surface without resolving those prerequisites.

## Decision

Do not add Tauri yet. Continue shipping the Python wheel, source archive and unhosted web archive.
Reconsider Tauri only after all of these evidence gates are met:

1. `scripts/platform_smoke.py` passes on a real Windows runner or machine.
2. The API has a documented start/stop, data-directory, migration and recovery lifecycle suitable
   for an embedded sidecar. **Satisfied locally in v0.10.0 by `docs/embedded-lifecycle.md`; Windows
   behavior remains part of gate 1.**
3. Installer signing, update rollback and supported OS versions have named owners.
4. Production packaging is qualified independently of the desktop wrapper.

## Consequences

Proofline remains a local web/API pre-alpha and does not claim desktop application support. This
avoids prematurely adding Rust, platform installers and updater complexity. Desktop capture remains
a later roadmap item rather than implemented behavior.

The platform-aware `proofline launch` command added in v0.14.13 does not change this decision. It
provides an application-data directory, loopback dynamic port, OS-keyring default and browser launch
from the installed Python wheel, but it does not create a native shell, installer, signature or
update channel.

## Revisit in v0.14.15

The user explicitly requested the remaining implementation work, and the embedded lifecycle plus
support-boundary prerequisites now exist. Proofline therefore adds an experimental Tauri shell and
current-platform build tooling. This does not waive the unsatisfied evidence gates: the macOS
artifact is ad-hoc signed rather than notarized, Windows has no real-machine receipt, and installer
update rollback and production packaging remain unqualified.
