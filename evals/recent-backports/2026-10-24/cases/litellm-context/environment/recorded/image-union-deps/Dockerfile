FROM sha256:7ef882ee8971a636c34ebd40597a65b7acc04f620c9fd8f7186602665cbdfde7
COPY requirements-common.txt /tmp/requirements-common.txt
COPY requirements-source-mcp.txt /tmp/requirements-source-mcp.txt
RUN python -m pip install --no-cache-dir --no-deps -r /tmp/requirements-common.txt
RUN python -m pip install --no-cache-dir --no-deps --target /opt/source-mcp -r /tmp/requirements-source-mcp.txt
COPY staged_layout.py /usr/local/lib/python3.12/site-packages/staged_layout.py
