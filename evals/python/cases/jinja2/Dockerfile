FROM --platform=linux/amd64 python:3.12.12-slim@sha256:42f1689d6d6b906c7e829f9d9ec38491550344ac9adc01e464ff9a08df1ffb48
COPY requirements.lock /tmp/requirements.lock
ADD https://files.pythonhosted.org/packages/56/43/4ca9e49d27a1fcf6bece6f6aec0ea46bb9112489b93d4b688fb415457bdb/iniconfig-2.3.1-py3-none-any.whl /wheels/iniconfig-2.3.1-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/0a/0d/2454f072fae3b5a137c119abf15465d1771319dfe9e4acbb31722a0fff91/MarkupSafe-2.1.5-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl /wheels/MarkupSafe-2.1.5-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
ADD https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl /wheels/packaging-26.3-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/40/9e/2b38731e0fc536806f16490e1a12d7f0dc2a1235aa8cc07bcc75416a7daa/pluggy-1.7.0-py3-none-any.whl /wheels/pluggy-1.7.0-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/30/3d/64ad57c803f1fa1e963a7946b6e0fea4a70df53c1a7fed304586539c2bac/pytest-8.3.5-py3-none-any.whl /wheels/pytest-8.3.5-py3-none-any.whl
RUN python -m pip install --no-cache-dir --force-reinstall --no-index \
    --find-links=/wheels --require-hashes -r /tmp/requirements.lock \
    && python -m pip check \
    && rm -rf /wheels /tmp/requirements.lock
ENV PYTHONDONTWRITEBYTECODE=1
