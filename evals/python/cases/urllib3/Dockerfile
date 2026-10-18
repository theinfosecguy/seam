# Public linux/amd64 platform manifest; no source checkout or test fixtures.
FROM python:3.11-slim@sha256:e529028263dbe6910a2d96f7d2b8f5266385e917fd45d286ef166977c094a51e
COPY requirements.lock /tmp/requirements.lock
ADD https://files.pythonhosted.org/packages/f7/a4/4399daaf8f7dfee9d7c3327fdb0426ee041cc63edc358b93911ceb2bfc7a/cffi-2.1.1-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.whl \
    https://files.pythonhosted.org/packages/d3/69/2c833a049475e0a3444e94c7d0aca0aa51d166374a449b09e92ac98138de/cryptography-50.0.2-cp311-abi3-manylinux_2_34_x86_64.whl \
    https://files.pythonhosted.org/packages/5e/2e/b41d8a1a917d6581fc27a35d05561037b048e47df50f27f8ac9c7e27a710/freezegun-1.5.5-py3-none-any.whl \
    https://files.pythonhosted.org/packages/58/a2/bb081bab032533a855d44de1d56f8e8426114ff1ba5d1f07a438a0a654f8/idna-3.20-py3-none-any.whl \
    https://files.pythonhosted.org/packages/56/43/4ca9e49d27a1fcf6bece6f6aec0ea46bb9112489b93d4b688fb415457bdb/iniconfig-2.3.1-py3-none-any.whl \
    https://files.pythonhosted.org/packages/bd/d9/617e6af809bf3a1d468e0d58c3997b1dc219a9a9202e650d30c2fc85d481/mock-5.2.0-py3-none-any.whl \
    https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl \
    https://files.pythonhosted.org/packages/40/9e/2b38731e0fc536806f16490e1a12d7f0dc2a1235aa8cc07bcc75416a7daa/pluggy-1.7.0-py3-none-any.whl \
    https://files.pythonhosted.org/packages/90/11/0e6f11117525ff0eec40ebac3d313376f102df93ca44ad9e893ee85e4f89/pycparser-3.11-py3-none-any.whl \
    https://files.pythonhosted.org/packages/8d/59/b4572118e098ac8e46e399a1dd0f2d85403ce8bbaad9ec79373ed6badaf9/PySocks-1.7.1-py3-none-any.whl \
    https://files.pythonhosted.org/packages/51/ff/f6e8b8f39e08547faece4bd80f89d5a8de68a38b2d179cc1c4490ffa3286/pytest-7.4.4-py3-none-any.whl \
    https://files.pythonhosted.org/packages/9e/09/0bdd7d24b9d21453ad3364ae1efbd65082045bb6081b5fd5eade91a9b644/pytest_freezegun-0.4.2-py2.py3-none-any.whl \
    https://files.pythonhosted.org/packages/ec/57/56b9bcc3c9c6a792fcbaf139543cee77261f3651ca9da0c93f5c1221264b/python_dateutil-2.9.0.post0-py2.py3-none-any.whl \
    https://files.pythonhosted.org/packages/d9/5a/e7c31adbe875f2abbb91bd84cf2dc52d792b5a01506781dbcf25c91daf11/six-1.16.0-py2.py3-none-any.whl \
    https://files.pythonhosted.org/packages/66/a5/e6da56c03ff61200d5a43cfb75ab09316fc0836aa7ee26b4e9dcbfc3ae85/tornado-6.3.3-cp38-abi3-manylinux_2_5_x86_64.manylinux1_x86_64.manylinux_2_17_x86_64.manylinux2014_x86_64.whl \
    https://files.pythonhosted.org/packages/e9/4b/abcebf9a03a05a82f48d9b63189c566727e1f72ddcc6dbfdd2314bb5cd08/trustme-1.1.0-py3-none-any.whl /tmp/wheels/
RUN python -m pip install --no-cache-dir --no-index --find-links=/tmp/wheels --require-hashes --only-binary=:all: --force-reinstall -r /tmp/requirements.lock \
    && python -m pip check \
    && rm -rf /tmp/wheels /tmp/requirements.lock
COPY urllib3_legacy_warnings.py /usr/local/lib/python3.11/site-packages/urllib3_legacy_warnings.py
