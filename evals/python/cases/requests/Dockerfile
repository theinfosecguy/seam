FROM --platform=linux/amd64 python:3.10-slim@sha256:7b6bd969dda3ecfca0655524e338b57a8b8cd692a9362e3d55b5a3ef49b07256
COPY requirements.lock /tmp/requirements.lock
ADD https://files.pythonhosted.org/packages/64/b4/17d4b0b2a2dc85a6df63d1157e028ed19f90d4cd97c36717afef2bc2f395/attrs-26.1.0-py3-none-any.whl /wheels/attrs-26.1.0-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/e4/37/af0d2ef3967ac0d6113837b44a4f0bfe1328c2b9763bd5b1744520e5cfed/certifi-2025.10.5-py3-none-any.whl /wheels/certifi-2025.10.5-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/0a/4c/925909008ed5a988ccbb72dcc897407e5d6d3bd72410d69e051fc0c14647/charset_normalizer-3.4.4-py3-none-any.whl /wheels/charset_normalizer-3.4.4-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/0e/61/66938bbb5fc52dbdf84594873d5b51fb1f7c7794e9c0f5bd885f30bc507b/idna-3.11-py3-none-any.whl /wheels/idna-3.11-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/56/43/4ca9e49d27a1fcf6bece6f6aec0ea46bb9112489b93d4b688fb415457bdb/iniconfig-2.3.1-py3-none-any.whl /wheels/iniconfig-2.3.1-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl /wheels/packaging-26.3-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/40/9e/2b38731e0fc536806f16490e1a12d7f0dc2a1235aa8cc07bcc75416a7daa/pluggy-1.7.0-py3-none-any.whl /wheels/pluggy-1.7.0-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/f6/f0/10642828a8dfb741e5f3fbaac830550a518a775c7fff6f04a007259b0548/py-1.11.0-py2.py3-none-any.whl /wheels/py-1.11.0-py2.py3-none-any.whl
ADD https://files.pythonhosted.org/packages/40/76/86f886e750b81a4357b6ed606b2bcf0ce6d6c27ad3c09ebf63ed674fc86e/pytest-6.2.5-py3-none-any.whl /wheels/pytest-6.2.5-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/44/6f/7120676b6d73228c96e17f1f794d8ab046fc910d781c8d151120c3f1569e/toml-0.10.2-py2.py3-none-any.whl /wheels/toml-0.10.2-py2.py3-none-any.whl
ADD https://files.pythonhosted.org/packages/33/cf/8435d5a7159e2a9c83a95896ed596f68cf798005fe107cc655b5c5c14704/urllib3-1.26.20-py2.py3-none-any.whl /wheels/urllib3-1.26.20-py2.py3-none-any.whl
RUN python -m pip install --no-cache-dir --force-reinstall --no-index \
    --find-links=/wheels --require-hashes -r /tmp/requirements.lock \
    && python -m pip check \
    && rm -rf /wheels /tmp/requirements.lock
ENV PYTHONDONTWRITEBYTECODE=1
