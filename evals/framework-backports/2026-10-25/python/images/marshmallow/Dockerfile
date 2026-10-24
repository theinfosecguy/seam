# Portable recipe; qualify the resulting new image/configuration separately.
FROM python@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c
COPY rebuild-requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt
COPY seam_expanded_settings.py /usr/local/lib/python3.12/site-packages/seam_expanded_settings.py
ENV DJANGO_SETTINGS_MODULE=seam_expanded_settings
