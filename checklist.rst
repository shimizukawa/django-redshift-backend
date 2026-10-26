.. release procedure

Procedure:

1. Review CI results and any known failures. The existing Ruff findings are not
   addressed by the 5.0.1.dev1 publishing-verification release; record this exception.
2. Update the version, date, and scope in ``CHANGES.rst`` and the version in
   ``doc/conf.py``. For 5.0.1.dev1, explicitly state that known functional problems
   remain unresolved and that this is a development release for publishing verification.
3. Build the wheel and source distribution with ``uv build`` and validate both
   with ``uvx twine check dist/*``. Check the version and project URLs in both
   distributions. Versioning uses setuptools-scm and Git tags; do not hard-code
   the package version in ``pyproject.toml``.
4. Confirm that PyPI has a Trusted Publisher for owner ``shimizukawa``, repository
   ``django-redshift-backend``, workflow filename ``release.yml``, and environment
   ``pypi``. Configure the matching GitHub environment and its deployment rules.
5. For optional TestPyPI verification, manually run the ``Release`` workflow on
   the desired branch. This publishes only to TestPyPI and requires its own
   Trusted Publisher and GitHub environment named ``testpypi``. The workflow
   must be present on the default branch for manual execution. Uploaded filenames
   cannot be reused; choose a new version for a subsequent upload.
6. Only when ready to publish, create and push the intended version tag, for
   example ``5.0.1.dev1``. Tag pushes trigger the production PyPI publishing job
   in ``.github/workflows/release.yml``. A GitHub Release is not the trigger.
   Verify the tagged build's version before pushing the tag; do not create a
   production tag merely to test the workflow.
7. If the ``pypi`` environment requires approval, review and approve the deployment.
   The workflow publishes the checked artifacts using OIDC and PEP 740 attestations;
   no Jazzband approval or release key is required.
8. Check the PyPI release page, wheel and source distribution, and attestations.
   In a clean environment, verify installation with an explicit version such as
   ``python -m pip install django-redshift-backend==5.0.1.dev1``. Record installation
   and functional verification separately: installation success does not establish
   that the backend works correctly with Redshift.
9. If creating a GitHub Release for a development version, mark it as a pre-release
   and repeat the known limitations in the release notes.

CI: https://github.com/shimizukawa/django-redshift-backend/actions

PyPI: https://pypi.org/project/django-redshift-backend/
