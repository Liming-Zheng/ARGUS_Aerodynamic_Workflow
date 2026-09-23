# GitHub release checklist

- [ ] Project owner approves public release.
- [ ] A software license is selected and added as `LICENSE`.
- [ ] NASA source-model redistribution is confirmed; otherwise remove
      `inputs/geometry/nasa_eet_ar12_original.vsp3` and provide a download link.
- [ ] Collaborator-owned RANS data, emails, personal information, and access URLs
      are absent.
- [ ] No university credentials, tokens, private URLs, or local usernames remain.
- [ ] `python tools/validate_repository.py` passes.
- [ ] Unit tests pass with the documented Python version.
- [ ] One geometry dry-run succeeds with a clean clone.
- [ ] One fixed-lift VSPAERO case succeeds with OpenVSP 3.50.1.
- [ ] Final summary CSV values match the approved report.
- [ ] Repository visibility (private/internal/public) is deliberately chosen.
- [ ] GitHub topics, description, DOI/release tag, and maintainer contact are set.

Recommended first release tag: `v1.0.0-handover`.


