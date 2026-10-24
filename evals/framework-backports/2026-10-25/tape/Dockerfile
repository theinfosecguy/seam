FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53
WORKDIR /opt/proof
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund --cache /tmp/npm-cache && rm -rf /tmp/npm-cache
ENV NODE_PATH=/opt/proof/node_modules
USER 65534:65534
WORKDIR /proof
