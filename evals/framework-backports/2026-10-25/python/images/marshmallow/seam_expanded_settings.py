"""Minimal public settings for selected original Django translation tests."""
import sys

sys.path.insert(0, '/work/repo/tests')
SECRET_KEY = 'public-translation-test-settings'
USE_I18N = True
LANGUAGE_CODE = 'en-us'
INSTALLED_APPS = ['i18n']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
LOCALE_PATHS = []
