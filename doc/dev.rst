===========
Development
===========

Contribution Guideline
======================

.. include:: ../CONTRIBUTING.rst

Issue Reporting
===============

**To Be Written**

* https://github.com/shimizukawa/django-redshift-backend/issues

Setup development environment
=============================

* Requires supported Python version
* do setup under django-redshift-backend.git repository root as::

    $ pip install uv
    $ uv sync

Testing
=======

Run test
--------

Just run tox::

   $ tox

tox have several sections for testing.

To test the database migration as well, start postgres and test it as follows::

   $ cd tests
   $ docker-compose up -d
   $ TEST_WITH_POSTGRES=1 tox

To test migrations with Redshift, do it as follows:

1. Create your redshift cruster on AWS
2. Get a redshift endpoint URI
3. run tox as: `TEST_WITH_REDSHIFT=redshift://user:password@<cluster>.<slug>.<region>.redshift.amazonaws.com:5439/<database>?DISABLE_SERVER_SIDE_CURSORS=True tox`

CI (Continuous Integration)
----------------------------

All tests will be run on Github Actions:

* https://github.com/shimizukawa/django-redshift-backend/actions?query=workflow%3ATest


Pull Request
============

**To Be Written**

* https://github.com/shimizukawa/django-redshift-backend/pulls


Build package
=============

Use build::

   $ uv build


Releasing
=========

New package version
-------------------

The django-redshift-backend package will be uploaded to PyPI: https://pypi.org/project/django-redshift-backend/.

Use the checklist below to track release readiness.

.. include:: ../checklist.rst


Release procedure
~~~~~~~~~~~~~~~~~

1. Review CI results and document any accepted known failures.
2. Update the version, date, scope, and known limitations in ``CHANGES.rst``.
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
6. Only when ready to publish, create and push the intended version tag. Tag pushes trigger the production PyPI publishing job
   in ``.github/workflows/release.yml``. A GitHub Release is not the trigger.
   Verify the tagged build's version before pushing the tag; do not create a
   production tag merely to test the workflow.
7. If the ``pypi`` environment requires approval, review and approve the deployment.
   The workflow publishes the checked artifacts using OIDC and PEP 740 attestations;
   no Jazzband approval or release key is required.
8. Check the PyPI release page, wheel and source distribution, and attestations.
   In a clean environment, verify installation with an explicit version such as
   ``python -m pip install django-redshift-backend==<version>``. Record installation
   and functional verification separately: installation success does not establish
   that the backend works correctly with Redshift.
9. If creating a GitHub Release for a development version, mark it as a pre-release
   and repeat the known limitations in the release notes.

CI: https://github.com/shimizukawa/django-redshift-backend/actions

PyPI: https://pypi.org/project/django-redshift-backend/


Updated documentation
---------------------

Sphinx documentation under ``doc/`` directory on the master branch will be automatically uploaded into ReadTheDocs: https://django-redshift-backend.rtfd.io/.

