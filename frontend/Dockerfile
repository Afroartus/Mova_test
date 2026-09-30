FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 4173

# `vite preview` sirve el build y reenvía /v1 y /health a API_PROXY_TARGET
# (ver vite.config.ts), así el navegador habla con un solo origen.
CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "4173"]
