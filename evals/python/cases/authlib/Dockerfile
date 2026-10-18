# Public linux/amd64 platform manifest; no source checkout or test fixtures.
FROM python:3.11-slim@sha256:e529028263dbe6910a2d96f7d2b8f5266385e917fd45d286ef166977c094a51e
COPY requirements.lock /tmp/requirements.lock
ADD https://files.pythonhosted.org/packages/f7/a4/4399daaf8f7dfee9d7c3327fdb0426ee041cc63edc358b93911ceb2bfc7a/cffi-2.1.1-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.whl \
    https://files.pythonhosted.org/packages/0e/e4/b3e68a4ac363406a56cf7b741eeb80d05284d8c60ee1a55cdc7587e2a553/cryptography-45.0.7-cp311-abi3-manylinux_2_34_x86_64.whl \
    https://files.pythonhosted.org/packages/56/43/4ca9e49d27a1fcf6bece6f6aec0ea46bb9112489b93d4b688fb415457bdb/iniconfig-2.3.1-py3-none-any.whl \
    https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl \
    https://files.pythonhosted.org/packages/40/9e/2b38731e0fc536806f16490e1a12d7f0dc2a1235aa8cc07bcc75416a7daa/pluggy-1.7.0-py3-none-any.whl \
    https://files.pythonhosted.org/packages/90/11/0e6f11117525ff0eec40ebac3d313376f102df93ca44ad9e893ee85e4f89/pycparser-3.11-py3-none-any.whl \
    https://files.pythonhosted.org/packages/c8/a9/8862616a85cf450d2822dbd4fff1fcaba90877907a6ff5bc2672cafe42f8/pycryptodomex-3.23.0-cp37-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl \
    https://files.pythonhosted.org/packages/30/3d/64ad57c803f1fa1e963a7946b6e0fea4a70df53c1a7fed304586539c2bac/pytest-8.3.5-py3-none-any.whl /tmp/wheels/
RUN python -m pip install --no-cache-dir --no-index --find-links=/tmp/wheels --require-hashes --only-binary=:all: --force-reinstall -r /tmp/requirements.lock \
    && python -m pip check \
    && rm -rf /tmp/wheels /tmp/requirements.lock
