===================
Design Overview
===================

Purpose
========

`django-redshift-backend` provides a backend for integrating Amazon Redshift database with the Django framework. It allows Django applications to use Redshift as their database while maintaining compatibility with Django's ORM and database abstraction layer.

Version 6 architecture
======================

Version 6 uses AWS's official ``redshift-connector`` driver and Django's
public database-backend APIs. The package no longer vendors Django's database
backend implementation and does not depend on psycopg2. The public backend
name remains ``django_redshift_backend`` so existing ``DATABASES`` settings
continue to select the backend.

The initial release supports username/password authentication. IAM and
identity-provider authentication are intentionally deferred.

Key Components of django-redshift-backend
=============================================

1. **Custom Database Backend**

   - Extends Django public base backend classes
   - Implements Redshift-specific functionality
   - Handles differences between PostgreSQL and Redshift

2. **SQL Compiler**

   - Modifies SQL generation to be compatible with Redshift
   - Handles Redshift-specific SQL syntax and limitations

3. **Schema Editor**

   - Customizes schema migrations for Redshift
   - Manages Redshift-specific data types and constraints

Design Principles
====================

1. **Compatibility**: Maintain maximum compatibility with Django's existing PostgreSQL backend
2. **Transparency**: Allow developers to use Django's ORM without significant changes to their code
3. **Flexibility**: Support Redshift-specific features where possible

Key Challenges
==============

1. **Version Compatibility**:
   Django 4.2.30 support uses a narrowly isolated compatibility path that can
   be removed when that release line is no longer supported.

2. **SQL Differences**: 
   Handle syntactical and functional differences between PostgreSQL and Redshift. Particularly, some PostgreSQL DDL (Data Definition Language) statements are not compatible with Redshift, requiring adjustments in areas such as table creation and constraint handling.

3. **Data Type Mapping**: 
   Map Django field types to appropriate Redshift data types. This is crucial as Redshift has different data types and limitations compared to standard PostgreSQL.

Implementation Strategy
=======================

1. Use only Django's public backend base classes.
2. Override the database operations and schema editor for Redshift SQL.
3. Preserve public ``DistKey`` and ``SortKey`` migration serialization paths.
4. Keep Django 4.2-only compatibility code isolated from common behavior.

Testing and Validation
========================

1. Unit tests for Redshift-specific functionality and limitations
2. Integration tests with actual Redshift instances
3. Compatibility testing with supporting Django and Python versions
4. Operational verification in common Django application scenarios

Future Considerations
============================

1. Live verification against a real Redshift cluster remains a future task.

2. Remove the isolated Django 4.2 compatibility path when support for that
   release line is eventually dropped.
