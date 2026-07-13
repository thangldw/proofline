# Security Policy

Proofline is pre-alpha and has not received a security audit. Do not expose the
development server directly to the public internet or use it for irreplaceable
or highly sensitive production data.

The repository-scoped trust boundaries, attacker assumptions, and severity
calibration are documented in [the security threat model](docs/security-threat-model.md).

## Supported versions

Proofline publishes experimental pre-releases. Security fixes target the default branch and the
latest pre-release on a best-effort basis; there are no maintenance or backport commitments.

| Version | Support status |
| --- | --- |
| Default branch | Best-effort pre-alpha fixes |
| `v0.14.9` | Best effort until the next pre-release |
| Older tags and local forks | Not supported |

## Report a vulnerability privately

Do not file a public issue, discussion, or pull request for a suspected
vulnerability.

1. Prefer GitHub's private vulnerability-reporting form under the repository's
   **Security** tab when that option is available.
2. If private reporting is unavailable, use the repository maintainer's private
   contact method shown on their GitHub profile. Initially send only a short
   description and request a secure channel; do not place an exploit, secret, or
   private source content in a public or unconfirmed channel.
3. Include the affected revision or version, impact, prerequisites, minimal
   reproduction using synthetic data, and any proposed mitigation.

Never include third-party credentials, personal data, proprietary vault content,
raw model prompts or responses, or data taken from a system you do not own.

There is no response-time SLA during pre-alpha. Maintainers will make a
best-effort attempt to acknowledge a private report, reproduce it safely, assess
affected revisions, and coordinate remediation and disclosure. A reporter may
request attribution or anonymity.

## Coordinated disclosure

Please allow maintainers a reasonable opportunity to investigate and prepare a
fix before public disclosure. Maintainers should communicate whether the report
is accepted, rejected, or requires more evidence, and should avoid asking a
reporter to transmit sensitive production data.

Security research must use systems and data the researcher owns or is authorized
to test. Do not degrade services, persist access, exfiltrate data, or expand a
proof of concept beyond what is necessary to demonstrate impact.
