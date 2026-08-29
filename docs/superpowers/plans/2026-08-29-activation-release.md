# Activation and 6.0 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task.

**Goal:** Activate the driver backend as the public ENGINE and publish 6.0 metadata without forcing schema migration.

**Architecture:** Re-export the internal wrapper from `base.py`, retain public key APIs, remove the old psycopg2/vendored implementation, and make package metadata name the official driver.

**Spec:** `docs/superpowers/specs/2026-08-29-activation-release-design.md`

### Task 1: Activation contract

- [ ] Write a failing test proving `base.DatabaseWrapper is _backend.DatabaseWrapper` and migration-key imports are unchanged.
- [ ] Replace `base.py` with the compatibility re-export and run the focused test.
- [ ] Commit `feat: activate Redshift connector backend`.

### Task 2: Remove legacy implementation and update packaging

- [ ] Write failing tests asserting no package source imports psycopg2 or `_vendor`.
- [ ] Remove `_vendor` and `psycopg2adapter.py`; update `pyproject.toml` to Django `>=4.2.30,<6.2`, `redshift-connector>=2.1.14,<3`, and 6.0 classifiers.
- [ ] Regenerate `uv.lock`, run build/twine checks, and commit.

### Task 3: Release record and matrix

- [ ] Update release notes and documentation with 6.0 migration guidance and username/password-only scope.
- [ ] Run the 4.2.30/5.2/6.x driver matrix, migration compatibility tests, package build, and protected-API checks.
- [ ] Create/update the final stacked PR and tracking PR.
