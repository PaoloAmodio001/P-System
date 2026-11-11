# A node of P-System. Keys, certificates and the store come from a volume, never from the image.

# The core of the rounds is Lean code, compiled to a shared library and called by the node
# (network/quorum/lean_core.py). It is built here with the toolchain of formal/lean/lean-toolchain,
# pinned by its hash; the image keeps only the library and the Lean runtime.
FROM python:3.14-slim AS lean
ARG LEAN_VERSION=4.34.1
ARG LEAN_SHA256=47bf4bbd78f70c2e9670598ab7124d92b6efb7330ff33e5fbb4030f6fd72e4e4
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl zstd git \
    && rm -rf /var/lib/apt/lists/*
RUN curl -sSfL -o /tmp/lean.tar.zst \
        "https://github.com/leanprover/lean4/releases/download/v${LEAN_VERSION}/lean-${LEAN_VERSION}-linux.tar.zst" \
    && echo "${LEAN_SHA256}  /tmp/lean.tar.zst" | sha256sum -c - \
    && tar --zstd -xf /tmp/lean.tar.zst -C /opt \
    && mv "/opt/lean-${LEAN_VERSION}-linux" /opt/lean \
    && rm /tmp/lean.tar.zst
ENV PATH=/opt/lean/bin:$PATH
COPY formal/lean /src/formal/lean
RUN cd /src/formal/lean && lake build PSystem:shared

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

COPY --from=lean /src/formal/lean/.lake/build/lib/libPSystem_PSystem.so /opt/psystem/lib/
COPY --from=lean /opt/lean/lib/lean/libleanshared.so /opt/lean/lib/lean/
ENV PSYSTEM_LEAN_CORE=/opt/psystem/lib/libPSystem_PSystem.so \
    PSYSTEM_LEAN_PREFIX=/opt/lean

USER psystem
WORKDIR /data
VOLUME /data
HEALTHCHECK --interval=15s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=4).status == 200 else 1)"
ENTRYPOINT ["psystem"]
CMD ["node", "--config", "/data/node.toml"]
