FROM python@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c
COPY wheels /wheels
RUN python -m pip install --no-index --no-cache-dir --find-links=/wheels /wheels/*.whl && rm -rf /wheels
COPY seam_django_settings.py /usr/local/lib/python3.12/site-packages/seam_django_settings.py
ENV DJANGO_SETTINGS_MODULE=seam_django_settings
