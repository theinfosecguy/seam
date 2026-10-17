"""Check the whitespace-key fix independently of the target checkout's tests."""

from jinja2 import Environment, Undefined


def test_security_whitespace_attribute_keys() -> None:
    template = Environment(autoescape=True).from_string(
        "<div{{ attrs|xmlattr }}></div>"
    )
    for whitespace in (" ", "\t", "\n", "\r", "\f", "\v"):
        key = f"data-safe{whitespace}onmouseover"
        try:
            template.render(attrs={key: "alert(1)"})
        except ValueError:
            continue
        raise AssertionError(
            "XMLATTR_WHITESPACE_SECURITY_REGRESSION: "
            f"attribute key containing {whitespace!r} was accepted"
        )


def test_control_valid_attributes_are_escaped() -> None:
    template = Environment(autoescape=True).from_string(
        "<div{{ attrs|xmlattr }}>ok</div>"
    )
    assert template.render(attrs={"data-id": 'a&"<>'}) == (
        '<div data-id="a&amp;&#34;&lt;&gt;">ok</div>'
    )


def test_control_none_and_undefined_are_omitted() -> None:
    template = Environment(autoescape=True).from_string(
        "<div{{ attrs|xmlattr }}></div>"
    )
    attrs = {
        "data-safe": "ok",
        "unused invalid key": None,
        "another invalid key": Undefined(name="missing"),
    }
    assert template.render(attrs=attrs) == '<div data-safe="ok"></div>'


def test_control_autospace_false_preserves_output() -> None:
    template = Environment(autoescape=True).from_string("{{ attrs|xmlattr(false) }}")
    assert template.render(attrs={"id": "example", "data-count": 0}) == (
        'id="example" data-count="0"'
    )
