"""Check that distinct overlong language strings share a bounded cache key."""
import pytest
from django.test import override_settings
from django.utils.translation import trans_real


def language_cache():
    return getattr(
        trans_real, '_get_supported_language_variant',
        trans_real.get_supported_language_variant,
    )


def test_security():
    with override_settings(LANGUAGES=[('en', 'English')], USE_I18N=True):
        cache = language_cache()
        cache.cache_clear()
        try:
            for suffix in ['a', 'b']:
                value = 'en-' + 'x' * 600 + suffix
                assert trans_real.get_supported_language_variant(value) == 'en'
            assert cache.cache_info().currsize == 1, 'LANGUAGE_CACHE_KEYS_TRUNCATED'
        finally:
            cache.cache_clear()


def test_supported_language():
    with override_settings(LANGUAGES=[('en', 'English')], USE_I18N=True):
        assert trans_real.get_supported_language_variant('en') == 'en'
        assert trans_real.get_supported_language_variant('en-gb') == 'en'


def test_unsupported_language():
    with override_settings(LANGUAGES=[('en', 'English')], USE_I18N=True):
        with pytest.raises(LookupError):
            trans_real.get_supported_language_variant('unknown')
        with pytest.raises(LookupError):
            trans_real.get_supported_language_variant('en-' + 'x' * 600, strict=True)
