=====
Basic
=====

Installation
============

Please install django-redshift-backend with using pip (8.1.1 or later).

.. code-block:: bash

   $ pip install django-redshift-backend

This backend uses AWS's official ``redshift-connector`` Python driver, which
is installed automatically with this package:

.. code-block:: bash

   $ pip install django-redshift-backend

The initial 6.0 release supports username/password authentication. IAM and
identity-provider authentication are deferred.

Django settings
===============

ENGINE for DATABASES is 'django_redshift_backend'. You can set the name in your settings.py as::

   DATABASES = {
       'default': {
           'ENGINE': 'django_redshift_backend',
           'NAME': '<your database name>',
           'USER': '<your database username>',
           'PASSWORD': '<your database password>',
           'HOST': '<your database hostname>',
           'PORT': '5439',
       }
   }

For more information, please refer :doc:`refs`.

TLS verification
================

When ``OPTIONS['sslmode']`` is omitted, the installed ``redshift-connector``
version determines TLS verification. Version 2.2.0 changes the default from
``verify-ca`` (certificate-chain verification) to ``verify-full`` (also checks
the hostname). In 2.2.0, an omitted mode permits a hostname mismatch with a
warning; AWS plans to reject such mismatches in a future release.

Set ``OPTIONS = {'sslmode': 'verify-full'}`` to require both certificate-chain
and hostname verification explicitly. A mismatch then fails the connection.
Explicit ``verify-ca`` is also supported. These settings apply when TLS is
enabled; use the actual Redshift endpoint hostname for the connection.

See the `AWS connector changelog
<https://github.com/aws/amazon-redshift-python-driver/blob/master/CHANGELOG.md>`_.

