# Keep the coding toolchain independent of MiniSago application deployments.
FROM node:24-bookworm-slim AS node
FROM ghcr.io/sago-cream/minisago-worker:sha-c08df28e3cb3dae405ec91f6983535a6e71b7a91

USER root
RUN rm -f /usr/local/bin/node
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
  && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
  && apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*
ARG T3_VERSION=0.1.6
ARG T3_SHA256=b708f059200776f50623a766854841e40eda0bb67614211cf8b6909295ce20da
RUN curl -fsSL "https://github.com/pingdotgg/t3code/releases/download/v${T3_VERSION}/t3-${T3_VERSION}-linux-arm64.tar.gz" -o /tmp/t3.tar.gz \
  && echo "${T3_SHA256}  /tmp/t3.tar.gz" | sha256sum -c - \
  && mkdir -p /opt/t3 \
  && tar -xzf /tmp/t3.tar.gz --strip-components=1 -C /opt/t3 \
  && rm /tmp/t3.tar.gz \
  && ln -s /opt/t3/t3 /usr/local/bin/t3 \
  && /opt/t3/t3 --version
COPY entrypoint /usr/local/bin/t3-entrypoint
COPY authorize-bot.py /opt/t3/authorize-bot.py
RUN chmod 755 /usr/local/bin/t3-entrypoint
ENV T3CODE_HOME=/home/bun/.t3
ENV CODEX_HOME=/home/bun/.codex
ENV GH_CONFIG_DIR=/home/bun/.config/gh
ENV MINISAGO_DEPLOY_SOCKET=/run/sago-cloud/minisago-deploy.sock
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/t3-entrypoint"]
CMD ["t3", "serve", "--host", "0.0.0.0", "--port", "3773"]
