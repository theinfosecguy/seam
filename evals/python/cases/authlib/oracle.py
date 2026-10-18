import base64
import hashlib
import hmac
import json
from typing import Final

from authlib.jose import JsonWebSignature
from authlib.jose.errors import JoseError

KEY: Final = b"seam-regression-only-hmac-key-32bytes"
PAYLOAD: Final = b"ordinary regression fixture"


def token(header: dict[str, object]) -> bytes:
    def encode(value: bytes) -> bytes:
        return base64.urlsafe_b64encode(value).rstrip(b"=")

    signing_input = b".".join((encode(json.dumps(header).encode()), encode(PAYLOAD)))
    signature = hmac.new(KEY, signing_input, hashlib.sha256).digest()
    return signing_input + b"." + encode(signature)


def test_security_unknown_critical_header() -> None:
    verifier = JsonWebSignature(algorithms=["HS256"])
    for header in (
        {"alg": "HS256", "crit": ["bork"], "bork": "fixture"},
        {"alg": "HS256", "crit": ["kid"]},
    ):
        rejected = False
        try:
            verifier.deserialize_compact(token(header), KEY)
        except JoseError as error:
            assert "crit" in str(error).lower(), "unrelated JOSE rejection"
            rejected = True
        assert rejected, (
            "AUTHLIB_CRITICAL_HEADER_REGRESSION: unsupported critical header accepted"
        )


def test_control_normal_signed_payload() -> None:
    verifier = JsonWebSignature(algorithms=["HS256"])
    assert (
        verifier.deserialize_compact(token({"alg": "HS256"}), KEY)["payload"] == PAYLOAD
    )


def test_control_noncritical_private_header() -> None:
    verifier = JsonWebSignature(algorithms=["HS256"])
    header = {"alg": "HS256", "bork": "fixture"}
    assert verifier.deserialize_compact(token(header), KEY)["payload"] == PAYLOAD


def test_control_known_critical_header() -> None:
    verifier = JsonWebSignature(algorithms=["HS256"])
    header = {"alg": "HS256", "kid": "fixture", "crit": ["kid"]}
    assert verifier.deserialize_compact(token(header), KEY)["payload"] == PAYLOAD
