import pytest
from django.core.cache import caches
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.views.decorators.cache import cache_page, never_cache


@pytest.fixture(autouse=True)
def isolated_cache():
    with override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "vary-oracle"}},
        CACHE_MIDDLEWARE_ALIAS="default",
        CACHE_MIDDLEWARE_SECONDS=60,
        CACHE_MIDDLEWARE_KEY_PREFIX="vary-oracle",
        ALLOWED_HOSTS=["testserver"],
    ):
        caches["default"].clear()
        yield
        caches["default"].clear()


def cached_view(headers=None, never=False):
    calls = []

    def view(request):
        calls.append(request.headers.get("Accept-Language", "ordinary"))
        response = HttpResponse(f"response-{len(calls)}")
        for name, value in (headers or {}).items():
            response[name] = value
        return response

    return cache_page(60)(never_cache(view) if never else view), calls


def request(view, language=None):
    arguments = {"HTTP_ACCEPT_LANGUAGE": language} if language else {}
    response = view(RequestFactory().get("/ordinary/", **arguments))
    content = response.content
    response.close()
    return content


def test_security_regression():
    cached = []
    for vary in ("*", "Accept-Encoding, *", "*, Cookie"):
        caches["default"].clear()
        view, calls = cached_view({"Vary": vary})
        first = request(view)
        second = request(view)
        if first == second or len(calls) != 2:
            cached.append(vary)
    assert not cached, f"DJANGO_VARY_WILDCARD_REGRESSION: wildcard responses cached: {cached}"


def test_ordinary_response_cached():
    view, calls = cached_view()
    assert request(view) == request(view)
    assert len(calls) == 1


def test_non_wildcard_vary_preserved():
    view, calls = cached_view({"Vary": "Accept-Language"})
    english = request(view, "en")
    assert request(view, "en") == english
    french = request(view, "fr")
    assert french != english
    assert request(view, "fr") == french
    assert len(calls) == 2


def test_private_not_cached():
    view, calls = cached_view({"Cache-Control": "private"})
    assert request(view) != request(view)
    assert len(calls) == 2


def test_never_cache_preserved():
    view, calls = cached_view(never=True)
    assert request(view) != request(view)
    assert len(calls) == 2

