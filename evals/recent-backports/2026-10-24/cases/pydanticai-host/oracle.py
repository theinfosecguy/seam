from pathlib import Path

import pydantic_ai
import pydantic_ai.models
from pydantic_ai import Agent
from pydantic_ai.ui._web import create_web_app
from starlette.testclient import TestClient


assert Path(pydantic_ai.__file__).resolve().is_relative_to(
    Path('/work/repo/pydantic_ai_slim').resolve()
), 'The checked-out source package must be tested'
pydantic_ai.models.ALLOW_MODEL_REQUESTS = False


def health(host):
    app = create_web_app(Agent('test'))
    with TestClient(app, base_url='http://localhost') as client:
        return client.get('/api/health', headers={'Host': host})


def test_security_foreign_host():
    response = health('ui.example.invalid')
    assert response.status_code == 421, (
        'FOREIGN_HOST_REGRESSION: a foreign Host reached the local web UI'
    )


def test_control_localhost():
    response = health('localhost:7932')
    assert response.status_code == 200
    assert response.json() == {'ok': True}


def test_control_loopback_ipv6():
    response = health('[::1]:7932')
    assert response.status_code == 200
    assert response.json() == {'ok': True}


def test_control_lan_ip():
    response = health('192.168.1.2:7932')
    assert response.status_code == 200
    assert response.json() == {'ok': True}
