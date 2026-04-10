FROM postgres:16

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        curl \
        gnupg \
        ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY primary-api /workspace/primary-api
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir /workspace/primary-api \
    && /opt/venv/bin/pip install --no-cache-dir \
        httpx==0.28.1 \
        pydantic-settings==2.9.1 \
        docker==7.1.0

COPY agent /workspace/agent

COPY primary-web/package*.json /workspace/primary-web/
RUN cd /workspace/primary-web && npm install
COPY primary-web /workspace/primary-web

COPY primary/start-primary.sh /usr/local/bin/start-primary.sh
RUN chmod +x /usr/local/bin/start-primary.sh

ENV PATH="/opt/venv/bin:${PATH}"

EXPOSE 5432 8000 5173

ENTRYPOINT ["/usr/local/bin/start-primary.sh"]
