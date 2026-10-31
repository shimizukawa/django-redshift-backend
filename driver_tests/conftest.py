import django
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.configure(
            DATABASES={},
            DEFAULT_AUTO_FIELD="django.db.models.AutoField",
            INSTALLED_APPS=["tests.testapp"],
            SECRET_KEY="driver-contract",
            USE_TZ=False,
        )
    django.setup()
