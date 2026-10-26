.. release checklist

- [ ] Review CI results and known failures.
- [ ] Update ``CHANGES.rst`` and ``version = release`` in ``doc/conf.py``.
- [ ] Run ``uv build`` and ``uvx twine check dist/*``; check versions and project URLs.
- [ ] Confirm Trusted Publishing and environment settings (``pypi``; ``testpypi`` for testing).
- [ ] If needed, manually run the ``Release`` workflow to publish to TestPyPI.
- [ ] Create the version tag, verify the tagged build's version, then push the tag to publish to PyPI.
- [ ] Approve the deployment if required; check PyPI files, attestations, and installation.
- [ ] If creating a GitHub Release for a development version, mark it as a pre-release.
