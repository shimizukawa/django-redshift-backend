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


Updated documentation
---------------------

Sphinx documentation under ``doc/`` directory on the master branch will be automatically uploaded into ReadTheDocs: https://django-redshift-backend.rtfd.io/.

