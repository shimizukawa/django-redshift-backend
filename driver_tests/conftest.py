import django
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.configure(
            DATABASES={},
            INSTALLED_APPS=[],
            SECRET_KEY="driver-contract",
            USE_TZ=False,
        )
    django.setup()
