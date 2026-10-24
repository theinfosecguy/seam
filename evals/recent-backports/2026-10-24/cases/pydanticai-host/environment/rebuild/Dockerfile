# Portable rebuild recipe; not the historical image identity.
FROM python@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --no-deps setuptools==80.9.0 wheel==0.45.1
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation -r /tmp/requirements.txt
COPY metadata /opt/staged-metadata
COPY staged_layout.py /usr/local/lib/python3.12/site-packages/staged_layout.py
