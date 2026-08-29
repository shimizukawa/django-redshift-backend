===========
Development
===========

Contribution Guideline
======================

.. include:: ../CONTRIBUTING.rst

Issue Reporting
===============

**To Be Written**

* https://github.com/jazzband/django-redshift-backend/issues

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

The test suite validates generated migration SQL without a database server.
The ``driver_tests`` migration corpus replays the existing ``tests/testapp``
migrations and protects their serialized public API paths. Live verification
against Redshift is a future task.

CI (Continuous Integration)
----------------------------

All tests will be run on Github Actions:

* https://github.com/jazzband/django-redshift-backend/actions?query=workflow%3ATest


Pull Request
============

**To Be Written**

* https://github.com/jazzband/django-redshift-backend/pulls


Build package
=============

Use build::

   $ uv build


Releasing
=========

New package version
-------------------

The django-redshift-backend package will be uploaded to PyPI: https://pypi.org/project/django-redshift-backend/.

Here is a release procefure for releasing.

.. include:: ../checklist.rst


Updated documentation
---------------------

Sphinx documentation under ``doc/`` directory on the master branch will be automatically uploaded into ReadTheDocs: https://django-redshift-backend.rtfd.io/.

