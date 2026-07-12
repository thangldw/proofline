## Outcome

What user-visible or operator-visible behavior changed?

## Scope

What is deliberately not included? Link the approved issue or milestone.

## Design and provenance

Which contracts, migrations, source identities, spans, citations, review states,
or provider boundaries are affected?

## Verification

List exact commands and results. Include evaluation deltas only with the dataset
version and configuration needed to reproduce them.

- [ ] Focused tests cover success and failure behavior.
- [ ] `make test` passed.
- [ ] `make check` passed.
- [ ] A user-visible path was exercised when applicable.

## Risk and recovery

Describe migration, compatibility, privacy, security, remote-egress, deletion,
rollback, and recovery concerns. Write `None` only after considering each boundary.

## Documentation and release note

- [ ] User-visible configuration or behavior is documented.
- [ ] `CHANGELOG.md` is updated, or this change does not need a release note.
- [ ] Planned behavior is not presented as implemented.

## Sensitive-data check

- [ ] This change contains no credentials, private pilot data, proprietary source
      content, unredacted model output, or sensitive screenshots.
