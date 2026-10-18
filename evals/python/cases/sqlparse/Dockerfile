FROM --platform=linux/amd64 python:3.11-slim@sha256:e529028263dbe6910a2d96f7d2b8f5266385e917fd45d286ef166977c094a51e
COPY requirements.lock /tmp/requirements.lock
ADD https://files.pythonhosted.org/packages/56/43/4ca9e49d27a1fcf6bece6f6aec0ea46bb9112489b93d4b688fb415457bdb/iniconfig-2.3.1-py3-none-any.whl /wheels/iniconfig-2.3.1-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl /wheels/packaging-26.3-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/40/9e/2b38731e0fc536806f16490e1a12d7f0dc2a1235aa8cc07bcc75416a7daa/pluggy-1.7.0-py3-none-any.whl /wheels/pluggy-1.7.0-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/51/ff/f6e8b8f39e08547faece4bd80f89d5a8de68a38b2d179cc1c4490ffa3286/pytest-7.4.4-py3-none-any.whl /wheels/pytest-7.4.4-py3-none-any.whl
RUN python -m pip install --no-cache-dir --force-reinstall --no-index \
    --find-links=/wheels --require-hashes -r /tmp/requirements.lock \
    && python -m pip check \
    && rm -rf /wheels /tmp/requirements.lock
ENV PYTHONDONTWRITEBYTECODE=1
