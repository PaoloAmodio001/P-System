# A node of P-System with the tools of the network lab: scripts/netem_lab.py. Not for a real deployment.
FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 psystem

WORKDIR /opt/psystem
COPY requirements.lock pyproject.toml README.md ./
COPY core /opt/psystem/core
COPY crypto /opt/psystem/crypto
COPY network /opt/psystem/network
COPY sdk /opt/psystem/sdk
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps .

WORKDIR /data
ENTRYPOINT ["psystem"]
