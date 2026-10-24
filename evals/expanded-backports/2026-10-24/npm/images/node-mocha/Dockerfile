FROM node@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53
WORKDIR /opt/seam
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
