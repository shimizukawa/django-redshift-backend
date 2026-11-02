# Activation and 6.0 Release Implementation Plan

**Goal:** Activate the driver backend as the public ENGINE and publish 6.0 metadata without forcing schema migration.

## Acceptance criteria

| Area | Required outcome |
| --- | --- |
| Public activation | Existing ENGINE and historical migration imports select the redesigned backend. |
| Removal and packaging | Legacy driver/vendor code is absent and distribution metadata declares the release scope. |
| Compatibility | Supported version checks pass without automatic schema changes. |

## Verification checklist

Each item states the decision gate before the detailed implementation examples.
The references retain the commands and technical expectations for that item.

### 1. Activation contract

**Purpose:** Activate the redesigned wrapper through the established public entry point.

**Pass condition:** base.DatabaseWrapper is the internal wrapper; historical key-import identities remain valid.

**Verification:** Run activation and migration-import contracts. [Implementation and commands](#reference-1-activation-contract).

### 2. Remove legacy implementation and update packaging

**Purpose:** Remove the old driver/backend and declare release dependencies.

**Pass condition:** No runtime psycopg2 or vendored backend remains; metadata and distributions contain the intended implementation and dependency ranges.

**Verification:** Run removal, package metadata, build, and Twine checks. [Implementation and commands](#reference-2-remove-legacy-implementation-and-update-packaging).

### 3. Release record and matrix

**Purpose:** Publish compatibility guidance and verify release requirements.

**Pass condition:** Supported versions and password-only scope are clear; existing models/migrations require no automatic schema change.

**Verification:** Run the driver matrix, migration compatibility gates, and protected-API checks. [Implementation and commands](#reference-3-release-record-and-matrix).

## Implementation reference

The following scope, file map, examples, and commands support the checklist.
Intermediate failing examples describe the implementation sequence; they are
not the pass condition for the completed component.

**Architecture:** Re-export the internal wrapper from `base.py`, retain public key APIs, remove the old psycopg2/vendored implementation, and make package metadata name the official driver.

**Spec:** `docs/superpowers/specs/2026-08-29-activation-release-design.md`

### Reference 1: Activation contract

- [ ] Write a failing test proving `base.DatabaseWrapper is _backend.DatabaseWrapper` and migration-key imports are unchanged.
- [ ] Replace `base.py` with the compatibility re-export and run the focused test.

### Reference 2: Remove legacy implementation and update packaging

- [ ] Write failing tests asserting no package source imports psycopg2 or `_vendor`.
- [ ] Remove `_vendor` and `psycopg2adapter.py`; update `pyproject.toml` to Django `>=4.2`, `redshift-connector>=2.1.14,<3`, and 6.0 classifiers.
- [ ] Regenerate `uv.lock` and run build/twine checks.

### Reference 3: Release record and matrix

- [ ] Update release notes and documentation with 6.0 migration guidance and username/password-only scope.
- [ ] Run the 4.2.30/5.2/6.x driver matrix, migration compatibility tests, package build, and protected-API checks.
