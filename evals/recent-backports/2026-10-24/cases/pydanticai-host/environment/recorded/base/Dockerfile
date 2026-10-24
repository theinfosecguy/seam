FROM python:3.12-slim
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
COPY staged-monorepo.pth /usr/local/lib/python3.12/site-packages/staged-monorepo.pth
