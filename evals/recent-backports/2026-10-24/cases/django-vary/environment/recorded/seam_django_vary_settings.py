import sys

# Django's cache tests use the top-level cache application namespace.
sys.path.insert(0, "/work/repo/tests")
SECRET_KEY = "public-django-cache-test-settings"
USE_I18N = False
INSTALLED_APPS = ["cache"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
ALLOWED_HOSTS = ["testserver"]
