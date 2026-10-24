from django.core.exceptions import ValidationError
from django.core.validators import DomainNameValidator


def rejected(validator, value):
    try:
        validator(value)
    except ValidationError:
        return True
    return False


def test_security_regression():
    accepted = []
    for accept_idna in (True, False):
        validator = DomainNameValidator(accept_idna=accept_idna)
        for value in ("example.com\n", "example.com\r\n"):
            if not rejected(validator, value):
                accepted.append((accept_idna, repr(value)))
    assert not accepted, f"DJANGO_DOMAIN_NEWLINE_REGRESSION: {accepted}"


def test_ordinary_ascii_domains():
    for accept_idna in (True, False):
        validator = DomainNameValidator(accept_idna=accept_idna)
        for value in ("example.com", "DJANGOPROJECT.COM", "sub.example.co.uk"):
            assert validator(value) is None


def test_idna_modes():
    for value in ("ıçğü.com", "例子.测试"):
        assert DomainNameValidator()(value) is None
        assert rejected(DomainNameValidator(accept_idna=False), value)
    assert DomainNameValidator(accept_idna=False)("xn--7ca6byfyc.com") is None


def test_invalid_domains_preserved():
    for value in ("not-domain-name", "python..org", "python-.org"):
        assert rejected(DomainNameValidator(), value)
