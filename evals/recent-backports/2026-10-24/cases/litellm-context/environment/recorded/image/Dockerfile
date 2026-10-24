FROM python:3.12-slim
ENV LITELLM_MODE=PRODUCTION LITELLM_LOCAL_MODEL_COST_MAP=True AWS_EC2_METADATA_DISABLED=true LITELLM_CLI_DISABLE_KEYRING=1
COPY requirements-locked.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
COPY staged-monorepo.pth /usr/local/lib/python3.12/site-packages/staged-monorepo.pth
