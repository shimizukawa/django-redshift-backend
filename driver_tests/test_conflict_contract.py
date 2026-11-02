from types import SimpleNamespace

import pytest
from django.db import models
from django.db.models import query as query_module
from django.db.models.fields import related_descriptors
from django.db.models.query import QuerySet
from django.db.utils import NotSupportedError

from django_redshift_backend._backend import DatabaseWrapper


class Target(models.Model):
    class Meta:
        app_label = "driver_contract"


class Source(models.Model):
    targets = models.ManyToManyField(Target)

    class Meta:
        app_label = "driver_contract"


def settings_dict():
    return {
        "NAME": "warehouse",
        "HOST": "example.test",
        "PORT": "5439",
        "USER": "alice",
        "PASSWORD": "secret",
        "OPTIONS": {},
        "TIME_ZONE": None,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "AUTOCOMMIT": True,
    }


def fake_connections():
    wrapper = DatabaseWrapper(settings_dict(), "redshift-contract")
    return {"redshift-contract": SimpleNamespace(features=wrapper.features)}


def test_explicit_ignore_conflicts_fails_before_sql(monkeypatch):
    monkeypatch.setattr(query_module, "connections", fake_connections())
    queryset = QuerySet(model=Target, using="redshift-contract")
    with pytest.raises(NotSupportedError, match="does not support ignoring conflicts"):
        queryset._check_bulk_create_options(True, False, None, None)


def test_many_to_many_add_uses_existing_row_precheck(monkeypatch):
    connections = fake_connections()
    monkeypatch.setattr(related_descriptors, "connections", connections)
    manager = Source(pk=1).targets

    can_ignore_conflicts, must_send_signals, can_fast_add = manager._get_add_plan(
        "redshift-contract", manager.source_field_name
    )

    assert can_ignore_conflicts is False
    assert must_send_signals is False
    assert can_fast_add is False


def test_no_operation_generates_on_conflict():
    wrapper = DatabaseWrapper(settings_dict(), "redshift-contract")
    suffix = wrapper.ops.on_conflict_suffix_sql([], None, [], [])
    assert suffix == ""
    assert "CONFLICT" not in suffix
