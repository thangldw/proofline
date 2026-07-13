# ADR 0003: Defer Tauri desktop packaging

- Status: accepted
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
   for an embedded sidecar.
3. Installer signing, update rollback and supported OS versions have named owners.
4. Production packaging is qualified independently of the desktop wrapper.

## Consequences

Proofline remains a local web/API pre-alpha and does not claim desktop application support. This
avoids prematurely adding Rust, platform installers and updater complexity. Desktop capture remains
a later roadmap item rather than implemented behavior.
