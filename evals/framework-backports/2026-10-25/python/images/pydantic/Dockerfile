FROM python@sha256:03dee9ce00747bb5390e7b4ad00307b4dbc7790f7da77cc3581f93cfa99a6363
COPY wheels /opt/frozen-wheels
COPY requirements.txt /opt/frozen-requirements.txt
RUN python -m pip install --no-cache-dir --no-index --find-links=/opt/frozen-wheels --require-hashes --no-deps -r /opt/frozen-requirements.txt
