# Governance

Aethens is maintained by [@beastrog](https://github.com/beastrog) (Ani). While the project is
small, that maintainer is the final decision-maker for the roadmap, releases, and project direction.

## What needs maintainer approval

These changes must be called out in the pull request and approved by the maintainer before merge:

- Check semantics, report schema, severities, or thresholds
- Docker isolation settings or other sandbox guarantees
- The public API of the CLI, the GitHub Action inputs, or the task format
- Licence, trademark, or security-policy changes
- Adding a required dependency (especially one that is not permissively licensed)

## What the maintainer owns exclusively

Creating tags and GitHub releases, publishing to PyPI, changing repository visibility or billing,
and speaking for the project in a formal disclosure or partnership. Contributors should not do these.

## Contributions

Anyone can open issues and pull requests under the [code of conduct](CODE_OF_CONDUCT.md) and
[CONTRIBUTING.md](CONTRIBUTING.md). Merged contributions are licensed under Apache-2.0. There is no
CLA and no DCO.

## Future

If the project grows, maintainership may be shared and this document will be updated. Until then,
treat this as a single-maintainer project with a public issue tracker and a published audit trail
in `CHANGELOG.md`.
