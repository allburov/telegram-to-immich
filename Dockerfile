FROM ghcr.io/astral-sh/uv:python3.12-alpine

# https://github.com/iyear/tdl/releases
ARG TDL_VERSION=0.20.4
# https://github.com/simulot/immich-go/releases
ARG IMMICH_GO_VERSION=0.32.0

RUN apk add --no-cache tzdata \
    && wget -qO- "https://github.com/iyear/tdl/releases/download/v${TDL_VERSION}/tdl_Linux_64bit.tar.gz" \
       | tar -xz -C /usr/local/bin tdl \
    && wget -qO- "https://github.com/simulot/immich-go/releases/download/v${IMMICH_GO_VERSION}/immich-go_Linux_x86_64.tar.gz" \
       | tar -xz -C /usr/local/bin immich-go \
    && ln -s /data/tdl /root/.tdl

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src ./src
COPY scripts/sync-loop.sh ./scripts/

ENV PATH="/app/.venv/bin:$PATH" \
    MEDIA_PATH=/data/media \
    LOG_PATH=/data/logs \
    CONFIG_PATH=/data/config/tg-to-immich.yaml

CMD ["sh", "scripts/sync-loop.sh"]
