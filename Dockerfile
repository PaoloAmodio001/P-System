# A node of P-System. Keys, certificates and the store come from a volume, never from the image.
FROM python:3.14-slim

RUN useradd --create-home --uid 10001 psystem

WORKDIR /opt/psystem
COPY requirements.lock pyproject.toml README.md ./
COPY core /opt/psystem/core
COPY crypto /opt/psystem/crypto
COPY network /opt/psystem/network
COPY sdk /opt/psystem/sdk
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps .

USER psystem
WORKDIR /data
VOLUME /data
HEALTHCHECK --interval=15s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=4).status == 200 else 1)"
ENTRYPOINT ["psystem"]
CMD ["node", "--config", "/data/node.toml"]
