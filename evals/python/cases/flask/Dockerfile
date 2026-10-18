FROM --platform=linux/amd64 python:3.10-slim@sha256:7b6bd969dda3ecfca0655524e338b57a8b8cd692a9362e3d55b5a3ef49b07256
COPY requirements.lock /tmp/requirements.lock
ADD https://files.pythonhosted.org/packages/af/6d/ea3a5c3027c3f14b0321cd4f7e594c776ebe64e4b927432ca6917512a4f7/asgiref-3.5.2-py3-none-any.whl /wheels/asgiref-3.5.2-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/64/b4/17d4b0b2a2dc85a6df63d1157e028ed19f90d4cd97c36717afef2bc2f395/attrs-26.1.0-py3-none-any.whl /wheels/attrs-26.1.0-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/30/41/caa5da2dbe6d26029dfe11d31dfa8132b4d6d30b6d6b61a24824075a5f06/blinker-1.5-py2.py3-none-any.whl /wheels/blinker-1.5-py2.py3-none-any.whl
ADD https://files.pythonhosted.org/packages/c2/f1/df59e28c642d583f7dacffb1e0965d0e00b218e0186d7858ac5233dce840/click-8.1.3-py3-none-any.whl /wheels/click-8.1.3-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/8a/0e/97c33bf5009bdbac74fd2beace167cab3f978feb69cc36f1ef79360d6c4e/exceptiongroup-1.3.1-py3-none-any.whl /wheels/exceptiongroup-1.3.1-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/56/43/4ca9e49d27a1fcf6bece6f6aec0ea46bb9112489b93d4b688fb415457bdb/iniconfig-2.3.1-py3-none-any.whl /wheels/iniconfig-2.3.1-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/68/5f/447e04e828f47465eeab35b5d408b7ebaaaee207f48b7136c5a7267a30ae/itsdangerous-2.1.2-py3-none-any.whl /wheels/itsdangerous-2.1.2-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/bc/c3/f068337a370801f372f2f8f6bad74a5c140f6fda3d9de154052708dd3c65/Jinja2-3.1.2-py3-none-any.whl /wheels/Jinja2-3.1.2-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/3d/66/2f636ba803fd6eb4cee7b3106ae02538d1e84a7fb7f4f8775c6528a87d31/MarkupSafe-2.1.2-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl /wheels/MarkupSafe-2.1.2-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
ADD https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl /wheels/packaging-26.3-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/40/9e/2b38731e0fc536806f16490e1a12d7f0dc2a1235aa8cc07bcc75416a7daa/pluggy-1.7.0-py3-none-any.whl /wheels/pluggy-1.7.0-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/b2/68/5321b5793bd506961bd40bdbdd0674e7de4fb873ee7cab33dd27283ad513/pytest-7.2.2-py3-none-any.whl /wheels/pytest-7.2.2-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/30/5f/2e5c564bd86349fe6b82ca840f46acf6f4bb76d79ba9057fce3d3e008864/python_dotenv-0.20.0-py3-none-any.whl /wheels/python_dotenv-0.20.0-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/60/3f/3e3f8fd0919249b0200c80fbc4f9a1e70be19f9883da71dfb7f8b9ab8aca/tomli-2.5.0-py3-none-any.whl /wheels/tomli-2.5.0-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl /wheels/typing_extensions-4.16.0-py3-none-any.whl
ADD https://files.pythonhosted.org/packages/c8/27/be6ddbcf60115305205de79c29004a0c6bc53cec814f733467b1bb89386d/Werkzeug-2.2.2-py3-none-any.whl /wheels/Werkzeug-2.2.2-py3-none-any.whl
RUN python -m pip install --no-cache-dir --force-reinstall --no-index \
    --find-links=/wheels --require-hashes -r /tmp/requirements.lock \
    && python -m pip check \
    && rm -rf /wheels /tmp/requirements.lock
ENV PYTHONDONTWRITEBYTECODE=1
